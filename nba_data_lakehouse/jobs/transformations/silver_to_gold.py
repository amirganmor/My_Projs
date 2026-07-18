"""
Silver → Gold transformations.

Creates analytics marts, ML feature tables, and data quality summaries
by combining cross-source silver facts and dimensions.
"""
from __future__ import annotations

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql import Window
from pyspark.sql.types import NullType, StringType

from jobs.common.logging_utils import get_logger
from jobs.common.schemas import SILVER_TABLES, GOLD_TABLES, GOLD_NS
from jobs.common.spark_session import get_spark, stop_spark


def _cast_null_columns(df: DataFrame) -> DataFrame:
    """Cast any NullType (void) columns to StringType so Iceberg can handle them."""
    for field in df.schema.fields:
        if isinstance(field.dataType, NullType):
            df = df.withColumn(field.name, F.col(field.name).cast(StringType()))
    return df

log = get_logger("transform.silver_to_gold")


def _ensure_namespace(spark: SparkSession) -> None:
    try:
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {GOLD_NS}")
    except Exception:
        pass


def _safe_read(spark: SparkSession, table: str) -> DataFrame | None:
    try:
        df = spark.table(table)
        if df.count() > 0:
            return df
    except Exception as e:
        log.warning(f"  Could not read {table}: {e}")
    return None


# ---------------------------------------------------------------------------
# Gold: Player Season Summary (analytics mart)
# ---------------------------------------------------------------------------

def build_player_season_summary(spark: SparkSession) -> int:
    """Comprehensive player-season mart combining all sources."""
    log.info("Building gold.player_season_summary...")

    stats = _safe_read(spark, SILVER_TABLES["fact_player_season_stats"])
    if stats is None:
        return 0

    cols = [c.upper() for c in stats.columns]
    stats_upper = stats
    for c in stats.columns:
        stats_upper = stats_upper.withColumnRenamed(c, c.upper())

    # Core columns to select
    select_cols = ["PLAYER_ID", "SEASON", "SEASON_ID"]
    for c in ["PLAYER_NAME", "TEAM_ABBREVIATION", "AGE", "GP", "MIN", "PTS",
              "REB", "AST", "STL", "BLK", "TOV", "FG_PCT", "FG3_PCT", "FT_PCT",
              "OFF_RATING", "DEF_RATING", "NET_RATING", "TS_PCT", "USG_PCT", "PIE", "PACE"]:
        if c in stats_upper.columns:
            select_cols.append(c)

    available = [c for c in select_cols if c in stats_upper.columns]
    summary = stats_upper.select(*available).dropDuplicates(["PLAYER_ID", "SEASON"])

    from jobs.common.ids import normalize_name
    from pyspark.sql.types import StringType as _ST
    udf_norm = F.udf(normalize_name, _ST())

    # Join with contracts for salary
    contracts = _safe_read(spark, SILVER_TABLES["fact_player_contracts"])
    if contracts is not None and "PLAYER_NAME" in summary.columns and "SEASON" in summary.columns:
        contracts_agg = (
            contracts
            .groupBy("player_name_normalized", "season")
            .agg(F.max("salary").alias("salary"))
            .withColumnRenamed("player_name_normalized", "_c_norm")
            .withColumnRenamed("season", "_c_season")
        )
        summary = summary.withColumn("_norm_name", udf_norm("PLAYER_NAME"))
        summary = summary.join(
            contracts_agg,
            (summary["_norm_name"] == contracts_agg["_c_norm"]) &
            (summary["SEASON"] == contracts_agg["_c_season"]),
            "left",
        ).drop("_c_norm", "_c_season", "_norm_name")
        log.info("  Merged salary data")

    # Join with injury summary
    injuries = _safe_read(spark, SILVER_TABLES["fact_player_injuries"])
    if injuries is not None and "PLAYER_NAME" in summary.columns and "SEASON" in summary.columns:
        inj_cols = injuries.columns
        name_col = next((c for c in inj_cols if "player_name" in c.lower()), None)
        season_col = next((c for c in inj_cols if "season" in c.lower() and c != "season_id"), None)
        missed_col = next((c for c in inj_cols if "games_missed" in c.lower()), None)

        if name_col and season_col and missed_col:
            inj_agg = (
                injuries
                .groupBy(
                    F.col(name_col).alias("_inj_player"),
                    F.col(season_col).alias("_inj_season"),
                )
                .agg(
                    F.sum(missed_col).alias("total_games_missed"),
                    F.count("*").alias("injury_count"),
                )
            )
            summary = summary.withColumn("_norm_name2", udf_norm("PLAYER_NAME"))
            inj_agg = inj_agg.withColumn("_inj_norm", udf_norm("_inj_player"))
            summary = summary.join(
                inj_agg,
                (summary["_norm_name2"] == inj_agg["_inj_norm"]) &
                (summary["SEASON"] == inj_agg["_inj_season"]),
                "left",
            ).drop("_inj_player", "_inj_season", "_norm_name2", "_inj_norm")
        log.info("  Merged injury data")

    # Only fillna for columns that actually exist
    fill_map = {"total_games_missed": 0, "injury_count": 0, "salary": 0}
    fill_map = {k: v for k, v in fill_map.items() if k in summary.columns}
    if fill_map:
        summary = summary.fillna(fill_map)
    summary = _cast_null_columns(summary)
    summary.writeTo(GOLD_TABLES["player_season_summary"]).using("iceberg").createOrReplace()
    count = summary.count()
    log.info(f"  gold.player_season_summary: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Gold: ML Feature Table — Value Model
# ---------------------------------------------------------------------------

def build_features_value_model(spark: SparkSession) -> int:
    """Feature table for predicting player market value (salary).

    For seasons without salary data, carry forward the player's last known
    salary so that the scoring job can evaluate recent seasons too.
    """
    log.info("Building gold.features_value_model...")

    summary = _safe_read(spark, GOLD_TABLES["player_season_summary"])
    if summary is None:
        return 0

    cols = summary.columns

    feature_cols = ["PLAYER_ID", "SEASON", "PLAYER_NAME"]
    for c in ["AGE", "GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV",
              "FG_PCT", "FG3_PCT", "FT_PCT", "TS_PCT", "USG_PCT",
              "OFF_RATING", "DEF_RATING", "NET_RATING", "PIE", "PACE",
              "total_games_missed", "injury_count", "salary"]:
        if c in cols:
            feature_cols.append(c)

    available = [c for c in feature_cols if c in cols]
    features = summary.select(*available)

    if "SEASON" in cols and "PLAYER_ID" in cols and "PTS" in cols:
        w = Window.partitionBy("PLAYER_ID").orderBy("SEASON")
        for stat in ["PTS", "REB", "AST", "MIN"]:
            if stat in cols:
                features = features.withColumn(f"prev_{stat}", F.lag(stat).over(w))

    # Treat salary=0 as missing (the summary table uses fillna(0) but
    # 0 means "no salary data", not "playing for free").
    if "salary" in features.columns:
        features = features.withColumn(
            "salary",
            F.when(F.col("salary") > 0, F.col("salary")),
        )
        # Carry forward last known salary so recent seasons get a proxy value
        w_sal = (Window.partitionBy("PLAYER_ID").orderBy("SEASON")
                 .rowsBetween(Window.unboundedPreceding, Window.currentRow))
        features = features.withColumn(
            "salary",
            F.coalesce(F.col("salary"), F.last("salary", ignorenulls=True).over(w_sal)),
        )
        features = features.filter(F.col("salary").isNotNull() & (F.col("salary") > 0))
    else:
        log.warning("  No salary column in player_season_summary — run seed_local_sources first")

    if features.count() == 0:
        log.warning("  features_value_model: no rows (missing salary data?)")
        return 0

    features = _cast_null_columns(features)
    features.writeTo(GOLD_TABLES["features_value_model"]).using("iceberg").createOrReplace()
    count = features.count()
    log.info(f"  gold.features_value_model: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Gold: ML Feature Table — Improvement Model
# ---------------------------------------------------------------------------

def build_features_improvement_model(spark: SparkSession) -> int:
    """Feature table for predicting player improvement next season.

    Training rows have next_PTS (historical seasons where we know the outcome).
    Scoring rows (latest season) have next_PTS=NULL — they are included so the
    scoring job can predict who will break out next.
    """
    log.info("Building gold.features_improvement_model...")

    summary = _safe_read(spark, GOLD_TABLES["player_season_summary"])
    if summary is None:
        return 0

    cols = summary.columns
    if "PLAYER_ID" not in cols or "SEASON" not in cols or "PTS" not in cols:
        log.warning("  Missing required columns for improvement features")
        return 0

    w = Window.partitionBy("PLAYER_ID").orderBy("SEASON")

    features = summary
    for stat in ["PTS", "REB", "AST", "MIN", "FG_PCT", "FG3_PCT", "TS_PCT", "USG_PCT", "NET_RATING", "PIE"]:
        if stat in cols:
            features = features.withColumn(f"prev_{stat}", F.lag(stat).over(w))
            features = features.withColumn(f"{stat}_delta", F.col(stat) - F.col(f"prev_{stat}"))

    features = features.withColumn("next_PTS", F.lead("PTS").over(w))
    features = features.withColumn("next_NET_RATING",
                                    F.lead("NET_RATING").over(w) if "NET_RATING" in cols else F.lit(None))

    # Composite improvement target: multi-stat relative improvement
    features = features.withColumn(
        "improved_flag",
        F.when(
            (F.col("next_PTS") - F.col("PTS") >= 2.0) & (F.col("GP") >= 20),
            1,
        ).otherwise(0),
    )

    # Keep rows that have a previous season (needed for delta features).
    # Do NOT filter out rows where next_PTS is NULL — those are the latest
    # season rows that the scoring job needs to predict on.
    features = features.filter(F.col("prev_PTS").isNotNull())

    features = _cast_null_columns(features)
    features.writeTo(GOLD_TABLES["features_improvement_model"]).using("iceberg").createOrReplace()
    count = features.count()
    log.info(f"  gold.features_improvement_model: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Gold: ML Feature Table — Trade Target Model
# ---------------------------------------------------------------------------

def build_features_trade_target(spark: SparkSession) -> int:
    """Feature table for trade target composite scoring."""
    log.info("Building gold.features_trade_target_model...")

    summary = _safe_read(spark, GOLD_TABLES["player_season_summary"])
    if summary is None:
        return 0

    cols = summary.columns

    features = summary.filter(F.col("GP") >= 10) if "GP" in cols else summary

    # Treat salary=0 as missing, then carry forward last known salary
    if "salary" in features.columns and "PLAYER_ID" in features.columns and "SEASON" in features.columns:
        features = features.withColumn(
            "salary",
            F.when(F.col("salary") > 0, F.col("salary")),
        )
        w_sal = (Window.partitionBy("PLAYER_ID").orderBy("SEASON")
                 .rowsBetween(Window.unboundedPreceding, Window.currentRow))
        features = features.withColumn(
            "salary",
            F.coalesce(F.col("salary"), F.last("salary", ignorenulls=True).over(w_sal)),
        )

    if "PTS" in cols and "REB" in cols and "AST" in cols:
        features = features.withColumn(
            "performance_score",
            (F.col("PTS") * 1.0 + F.col("REB") * 1.2 + F.col("AST") * 1.5 +
             F.coalesce(F.col("STL"), F.lit(0)) * 2.0 +
             F.coalesce(F.col("BLK"), F.lit(0)) * 2.0 -
             F.coalesce(F.col("TOV"), F.lit(0)) * 1.0),
        )

    if "salary" in cols and "PTS" in cols:
        features = features.withColumn(
            "contract_efficiency",
            F.when(F.col("salary") > 0,
                   F.col("performance_score") / (F.col("salary") / 1_000_000))
            .otherwise(F.lit(0)),
        )

    if "AGE" in cols:
        features = features.withColumn(
            "age_upside_score",
            F.when(F.col("AGE") <= 23, 10)
            .when(F.col("AGE") <= 25, 8)
            .when(F.col("AGE") <= 27, 6)
            .when(F.col("AGE") <= 30, 4)
            .when(F.col("AGE") <= 33, 2)
            .otherwise(1),
        )

    features = features.withColumn(
        "durability_score",
        F.when(F.coalesce(F.col("total_games_missed"), F.lit(0)) <= 5, 10)
        .when(F.col("total_games_missed") <= 15, 7)
        .when(F.col("total_games_missed") <= 30, 4)
        .otherwise(2),
    )

    features = _cast_null_columns(features)
    features.writeTo(GOLD_TABLES["features_trade_target_model"]).using("iceberg").createOrReplace()
    count = features.count()
    log.info(f"  gold.features_trade_target_model: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Gold: Source Coverage Summary
# ---------------------------------------------------------------------------

def build_source_coverage(spark: SparkSession) -> int:
    log.info("Building gold.source_coverage_summary...")
    mapping = _safe_read(spark, SILVER_TABLES["player_source_mapping"])
    if mapping is None:
        return 0

    coverage = mapping.groupBy("source_name").agg(
        F.countDistinct("player_id").alias("unique_players"),
        F.count("*").alias("total_records"),
    )
    coverage = _cast_null_columns(coverage)
    coverage.writeTo(GOLD_TABLES["source_coverage_summary"]).using("iceberg").createOrReplace()
    count = coverage.count()
    log.info(f"  gold.source_coverage_summary: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Gold: Data Quality Summary
# ---------------------------------------------------------------------------

def build_data_quality_summary(spark: SparkSession) -> int:
    log.info("Building gold.data_quality_summary...")
    rows = []

    for layer, tables in [("silver", SILVER_TABLES), ("gold", GOLD_TABLES)]:
        for name, table in tables.items():
            try:
                df = spark.table(table)
                rc = df.count()
                cc = len(df.columns)
                rows.append((layer, name, table, rc, cc, "ok"))
            except Exception:
                rows.append((layer, name, table, 0, 0, "missing"))

    if not rows:
        return 0

    quality_df = spark.createDataFrame(
        rows, ["layer", "table_name", "full_table_path", "row_count", "column_count", "status"]
    )
    quality_df = _cast_null_columns(quality_df)
    quality_df.writeTo(GOLD_TABLES["data_quality_summary"]).using("iceberg").createOrReplace()
    count = quality_df.count()
    log.info(f"  gold.data_quality_summary: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Run All
# ---------------------------------------------------------------------------

def run_all() -> dict[str, int]:
    spark = get_spark("silver_to_gold")
    _ensure_namespace(spark)

    counts = {}
    try:
        counts["player_season_summary"] = build_player_season_summary(spark)
        counts["features_value_model"] = build_features_value_model(spark)
        counts["features_improvement_model"] = build_features_improvement_model(spark)
        counts["features_trade_target"] = build_features_trade_target(spark)
        counts["source_coverage"] = build_source_coverage(spark)
        counts["data_quality"] = build_data_quality_summary(spark)
    finally:
        stop_spark(spark)

    log.info(f"Silver→Gold complete: {counts}")
    return counts


if __name__ == "__main__":
    run_all()
