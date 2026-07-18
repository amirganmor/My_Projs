"""
Bronze → Silver transformations.

Creates conformed dimensions and fact tables by merging all 6 source families
into canonical entities with unified IDs.
"""
from __future__ import annotations

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import NullType, StringType

from jobs.common.ids import (
    normalize_name, normalize_team_abbr, normalize_season,
    make_player_id, make_team_id, make_season_id, make_game_id,
)
from jobs.common.logging_utils import get_logger
from jobs.common.schemas import BRONZE_TABLES, SILVER_TABLES, SILVER_NS
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("transform.bronze_to_silver")

# Register UDFs
_udf_norm_name = F.udf(normalize_name, StringType())
_udf_norm_team = F.udf(normalize_team_abbr, StringType())
_udf_norm_season = F.udf(normalize_season, StringType())
_udf_player_id = F.udf(lambda pid: make_player_id(pid), StringType())
_udf_team_id = F.udf(lambda tid: make_team_id(tid), StringType())
_udf_season_id = F.udf(lambda s: make_season_id(s), StringType())
_udf_game_id = F.udf(lambda g: make_game_id(g), StringType())


def _cast_null_columns(df: DataFrame) -> DataFrame:
    """Cast any NullType (void) columns to StringType so Iceberg can handle them."""
    for field in df.schema.fields:
        if isinstance(field.dataType, NullType):
            df = df.withColumn(field.name, F.col(field.name).cast(StringType()))
    return df


def _ensure_namespace(spark: SparkSession) -> None:
    try:
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {SILVER_NS}")
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
# Dimension: Players
# ---------------------------------------------------------------------------

def build_dim_players(spark: SparkSession) -> int:
    """Unify player identity across all sources."""
    log.info("Building silver.dim_players...")

    frames = []

    # From NBA API players
    df = _safe_read(spark, BRONZE_TABLES["nba_api_players"])
    if df is not None:
        cols = df.columns
        pid_col = "PERSON_ID" if "PERSON_ID" in cols else "person_id"
        name_col = "DISPLAY_FIRST_LAST" if "DISPLAY_FIRST_LAST" in cols else "display_first_last"
        from_col = "FROM_YEAR" if "FROM_YEAR" in cols else "from_year"
        to_col = "TO_YEAR" if "TO_YEAR" in cols else "to_year"

        players_api = df.select(
            F.col(pid_col).alias("nba_api_player_id"),
            F.col(name_col).alias("player_name"),
            F.col(from_col).alias("from_year"),
            F.col(to_col).alias("to_year"),
        ).distinct()
        players_api = players_api.withColumn("source", F.lit("nba_api"))
        frames.append(players_api)

    # From rosters (Postgres)
    df = _safe_read(spark, BRONZE_TABLES["rosters"])
    if df is not None:
        cols = df.columns
        pid_col = "player_id" if "player_id" in cols else "PLAYER_ID"
        name_col = "player_name" if "player_name" in cols else "PLAYER_NAME"

        if pid_col in cols:
            players_roster = df.select(
                F.col(pid_col).cast("string").alias("nba_api_player_id"),
                F.col(name_col).alias("player_name"),
            ).distinct()
            players_roster = (
                players_roster
                .withColumn("from_year", F.lit(None).cast("string"))
                .withColumn("to_year", F.lit(None).cast("string"))
                .withColumn("source", F.lit("postgres_rosters"))
            )
            frames.append(players_roster)

    if not frames:
        log.warning("  No player data found in any bronze table")
        return 0

    from functools import reduce
    combined = reduce(DataFrame.unionByName, frames)

    # Canonical IDs and dedup
    combined = (
        combined
        .withColumn("player_id", _udf_player_id("nba_api_player_id"))
        .withColumn("player_name_normalized", _udf_norm_name("player_name"))
    )

    # Deduplicate: keep first occurrence per player_id
    dim = (
        combined
        .orderBy("source")
        .dropDuplicates(["player_id"])
        .select("player_id", "nba_api_player_id", "player_name",
                "player_name_normalized", "from_year", "to_year")
    )

    dim = _cast_null_columns(dim)
    dim.writeTo(SILVER_TABLES["dim_players"]).using("iceberg").createOrReplace()
    count = dim.count()
    log.info(f"  silver.dim_players: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Dimension: Teams
# ---------------------------------------------------------------------------

def build_dim_teams(spark: SparkSession) -> int:
    log.info("Building silver.dim_teams...")
    df = _safe_read(spark, BRONZE_TABLES["nba_api_teams"])
    if df is None:
        return 0

    cols = df.columns
    tid_col = "id" if "id" in cols else "ID"
    name_col = "full_name" if "full_name" in cols else "FULL_NAME"
    abbr_col = "abbreviation" if "abbreviation" in cols else "ABBREVIATION"
    conf_col = next((c for c in cols if "conference" in c.lower()), None)
    div_col = next((c for c in cols if "division" in c.lower()), None)
    city_col = next((c for c in cols if "city" in c.lower()), None)

    dim = df.select(
        _udf_team_id(F.col(tid_col).cast("string")).alias("team_id"),
        F.col(tid_col).alias("nba_api_team_id"),
        F.col(name_col).alias("team_name"),
        _udf_norm_team(F.col(abbr_col)).alias("team_abbr"),
        F.col(conf_col).alias("conference") if conf_col else F.lit(None).cast(StringType()).alias("conference"),
        F.col(div_col).alias("division") if div_col else F.lit(None).cast(StringType()).alias("division"),
        F.col(city_col).alias("city") if city_col else F.lit(None).cast(StringType()).alias("city"),
    ).distinct()

    dim = _cast_null_columns(dim)
    dim.writeTo(SILVER_TABLES["dim_teams"]).using("iceberg").createOrReplace()
    count = dim.count()
    log.info(f"  silver.dim_teams: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Dimension: Seasons
# ---------------------------------------------------------------------------

def build_dim_seasons(spark: SparkSession) -> int:
    log.info("Building silver.dim_seasons...")
    df = _safe_read(spark, BRONZE_TABLES["nba_api_player_season_stats"])
    if df is None:
        return 0

    seasons = df.select("season").distinct()
    dim = seasons.select(
        _udf_season_id("season").alias("season_id"),
        F.col("season"),
        F.substring("season", 1, 4).cast("int").alias("start_year"),
        (F.substring("season", 1, 4).cast("int") + 1).alias("end_year"),
    )

    dim = _cast_null_columns(dim)
    dim.writeTo(SILVER_TABLES["dim_seasons"]).using("iceberg").createOrReplace()
    count = dim.count()
    log.info(f"  silver.dim_seasons: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Fact: Player Season Stats (merged from API + Advanced + Historical)
# ---------------------------------------------------------------------------

def build_fact_player_season_stats(spark: SparkSession) -> int:
    """Merge base stats, advanced metrics, and historical data."""
    log.info("Building silver.fact_player_season_stats...")

    # Base stats from NBA API
    base = _safe_read(spark, BRONZE_TABLES["nba_api_player_season_stats"])
    if base is None:
        log.warning("  No base player season stats")
        return 0

    cols = base.columns
    # Standardize column names to lowercase
    for c in cols:
        base = base.withColumnRenamed(c, c.upper())
    cols = base.columns

    pid_col = "PLAYER_ID" if "PLAYER_ID" in cols else cols[0]
    base = base.withColumn("player_id", _udf_player_id(F.col(pid_col).cast("string")))
    base = base.withColumn("season_id", _udf_season_id("SEASON"))
    base = base.withColumn("team_abbr", _udf_norm_team(
        F.col("TEAM_ABBREVIATION") if "TEAM_ABBREVIATION" in cols else F.lit("UNK")
    ))

    # Advanced metrics
    adv = _safe_read(spark, BRONZE_TABLES["advanced_player_metrics"])
    if adv is not None:
        for c in adv.columns:
            adv = adv.withColumnRenamed(c, c.upper())
        adv_cols = adv.columns

        adv_pid = "PLAYER_ID" if "PLAYER_ID" in adv_cols else adv_cols[0]
        adv = adv.withColumn("player_id", _udf_player_id(F.col(adv_pid).cast("string")))
        adv = adv.withColumn("season_id", _udf_season_id("SEASON"))

        # Select only advanced-specific columns
        adv_select_cols = ["player_id", "season_id"]
        for c in ["OFF_RATING", "DEF_RATING", "NET_RATING", "AST_PCT", "AST_TO",
                   "AST_RATIO", "OREB_PCT", "DREB_PCT", "REB_PCT", "EFG_PCT",
                   "TS_PCT", "USG_PCT", "PACE", "PIE", "POSS"]:
            if c in adv_cols:
                adv_select_cols.append(c)

        if len(adv_select_cols) > 2:
            adv_subset = adv.select(*adv_select_cols).dropDuplicates(["player_id", "season_id"])
            base = base.join(adv_subset, on=["player_id", "season_id"], how="left")
            log.info("  Merged advanced metrics")

    # Select final columns
    fact = base.dropDuplicates(["player_id", "season_id"])
    fact = _cast_null_columns(fact)
    fact.writeTo(SILVER_TABLES["fact_player_season_stats"]).using("iceberg").createOrReplace()
    count = fact.count()
    log.info(f"  silver.fact_player_season_stats: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Fact: Player Game Stats
# ---------------------------------------------------------------------------

def build_fact_player_game_stats(spark: SparkSession) -> int:
    log.info("Building silver.fact_player_game_stats...")
    df = _safe_read(spark, BRONZE_TABLES["nba_api_player_gamelogs"])
    if df is None:
        return 0

    for c in df.columns:
        df = df.withColumnRenamed(c, c.upper())
    cols = df.columns

    pid_col = "PLAYER_ID" if "PLAYER_ID" in cols else cols[0]
    df = df.withColumn("player_id", _udf_player_id(F.col(pid_col).cast("string")))
    df = df.withColumn("season_id", _udf_season_id("SEASON"))

    if "GAME_ID" in cols:
        df = df.withColumn("game_id", _udf_game_id("GAME_ID"))

    fact = df.dropDuplicates(["player_id", "GAME_ID"] if "GAME_ID" in cols else ["player_id", "season_id"])
    fact = _cast_null_columns(fact)
    fact.writeTo(SILVER_TABLES["fact_player_game_stats"]).using("iceberg").createOrReplace()
    count = fact.count()
    log.info(f"  silver.fact_player_game_stats: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Fact: Player Contracts
# ---------------------------------------------------------------------------

def build_fact_player_contracts(spark: SparkSession) -> int:
    log.info("Building silver.fact_player_contracts...")
    df = _safe_read(spark, BRONZE_TABLES["contracts"])
    if df is None:
        return 0

    cols = df.columns
    name_col = next((c for c in cols if "player_name" in c.lower() or c.lower() == "player"), None)
    salary_col = next((c for c in cols if "salary" in c.lower()), None)
    season_col = next((c for c in cols if "season" in c.lower()), None)
    team_col = next((c for c in cols if "team" in c.lower()), None)

    if not all([name_col, salary_col, season_col]):
        log.warning(f"  Missing required columns. Available: {cols}")
        return 0

    fact = df.select(
        _udf_norm_name(F.col(name_col)).alias("player_name_normalized"),
        F.col(name_col).alias("player_name"),
        _udf_norm_season(F.col(season_col)).alias("season"),
        F.col(salary_col).cast("double").alias("salary"),
        _udf_norm_team(F.col(team_col)).alias("team_abbr") if team_col else F.lit("UNK").alias("team_abbr"),
    )
    fact = fact.withColumn("season_id", _udf_season_id("season"))

    fact = _cast_null_columns(fact)
    fact.writeTo(SILVER_TABLES["fact_player_contracts"]).using("iceberg").createOrReplace()
    count = fact.count()
    log.info(f"  silver.fact_player_contracts: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Fact: Player Injuries
# ---------------------------------------------------------------------------

def build_fact_player_injuries(spark: SparkSession) -> int:
    log.info("Building silver.fact_player_injuries...")
    df = _safe_read(spark, BRONZE_TABLES["injuries"])
    if df is None:
        return 0

    cols = df.columns
    name_col = next((c for c in cols if "player_name" in c.lower()), None)
    season_col = next((c for c in cols if "season" in c.lower()), None)

    if not name_col:
        return 0

    fact = df.withColumn("player_name_normalized", _udf_norm_name(F.col(name_col)))
    if season_col:
        fact = fact.withColumn("season_id", _udf_season_id(F.col(season_col)))

    fact = _cast_null_columns(fact)
    fact.writeTo(SILVER_TABLES["fact_player_injuries"]).using("iceberg").createOrReplace()
    count = fact.count()
    log.info(f"  silver.fact_player_injuries: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Fact: Player Shot Profiles
# ---------------------------------------------------------------------------

def build_fact_player_shot_profiles(spark: SparkSession) -> int:
    log.info("Building silver.fact_player_shot_profiles...")
    df = _safe_read(spark, BRONZE_TABLES["shot_chart_zones"])
    if df is None:
        return 0

    for c in df.columns:
        df = df.withColumnRenamed(c, c.upper())
    cols = df.columns

    if "PLAYER_ID" in cols:
        df = df.withColumn("player_id", _udf_player_id(F.col("PLAYER_ID").cast("string")))
    if "SEASON" in cols:
        df = df.withColumn("season_id", _udf_season_id("SEASON"))

    df = _cast_null_columns(df)
    df.writeTo(SILVER_TABLES["fact_player_shot_profiles"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  silver.fact_player_shot_profiles: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Fact: Team Results
# ---------------------------------------------------------------------------

def build_fact_team_results(spark: SparkSession) -> int:
    log.info("Building silver.fact_team_results...")
    df = _safe_read(spark, BRONZE_TABLES["nba_api_standings"])
    if df is None:
        # Try historical standings
        df = _safe_read(spark, BRONZE_TABLES["historical_team_standings"])
    if df is None:
        return 0

    for c in df.columns:
        df = df.withColumnRenamed(c, c.upper())
    cols = df.columns

    if "TEAMID" in cols:
        df = df.withColumn("team_id", _udf_team_id(F.col("TEAMID").cast("string")))
    elif "TEAM_ID" in cols:
        df = df.withColumn("team_id", _udf_team_id(F.col("TEAM_ID").cast("string")))

    if "SEASON" in cols:
        df = df.withColumn("season_id", _udf_season_id("SEASON"))

    df = _cast_null_columns(df)
    df.writeTo(SILVER_TABLES["fact_team_results"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  silver.fact_team_results: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Fact: Player Profiles (flattened scouting/context)
# ---------------------------------------------------------------------------

def build_fact_player_profiles(spark: SparkSession) -> int:
    log.info("Building silver.fact_player_profiles...")
    df = _safe_read(spark, BRONZE_TABLES["mongo_player_profiles"])
    if df is None:
        return 0

    df = _cast_null_columns(df)
    df.writeTo(SILVER_TABLES["fact_player_profiles"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  silver.fact_player_profiles: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Player Source Mapping
# ---------------------------------------------------------------------------

def build_player_source_mapping(spark: SparkSession) -> int:
    """Track which sources contributed data for each player."""
    log.info("Building silver.player_source_mapping...")

    source_checks = [
        (BRONZE_TABLES["nba_api_player_season_stats"], "nba_api", "PLAYER_ID"),
        (BRONZE_TABLES["advanced_player_metrics"], "advanced_metrics", "PLAYER_ID"),
        (BRONZE_TABLES["shot_chart_zones"], "shot_charts", "PLAYER_ID"),
    ]

    frames = []
    for table, source, pid_col in source_checks:
        df = _safe_read(spark, table)
        if df is not None:
            for c in df.columns:
                df = df.withColumnRenamed(c, c.upper())
            if pid_col.upper() in df.columns:
                sub = df.select(
                    _udf_player_id(F.col(pid_col.upper()).cast("string")).alias("player_id"),
                    F.lit(source).alias("source_name"),
                ).distinct()
                frames.append(sub)

    if not frames:
        return 0

    from functools import reduce
    mapping = reduce(DataFrame.unionByName, frames)
    mapping = _cast_null_columns(mapping)
    mapping.writeTo(SILVER_TABLES["player_source_mapping"]).using("iceberg").createOrReplace()
    count = mapping.count()
    log.info(f"  silver.player_source_mapping: {count:,} rows")
    return count


# ---------------------------------------------------------------------------
# Quality Checks
# ---------------------------------------------------------------------------

def run_quality_checks(spark: SparkSession) -> dict:
    """Basic quality checks on silver tables."""
    log.info("Running silver quality checks...")
    results = {}

    for name, table in SILVER_TABLES.items():
        try:
            df = spark.table(table)
            row_count = df.count()
            col_count = len(df.columns)
            null_counts = {}
            for col_name in df.columns[:5]:  # check first 5 columns
                nulls = df.filter(F.col(col_name).isNull()).count()
                if nulls > 0:
                    null_counts[col_name] = nulls
            results[name] = {
                "rows": row_count,
                "columns": col_count,
                "null_flags": null_counts,
            }
            log.info(f"  {name}: {row_count:,} rows, {col_count} cols")
        except Exception:
            results[name] = {"rows": 0, "columns": 0, "null_flags": {}}

    return results


# ---------------------------------------------------------------------------
# Run All
# ---------------------------------------------------------------------------

def run_all() -> dict[str, int]:
    spark = get_spark("bronze_to_silver")
    _ensure_namespace(spark)

    counts = {}
    try:
        counts["dim_players"] = build_dim_players(spark)
        counts["dim_teams"] = build_dim_teams(spark)
        counts["dim_seasons"] = build_dim_seasons(spark)
        counts["fact_player_season_stats"] = build_fact_player_season_stats(spark)
        counts["fact_player_game_stats"] = build_fact_player_game_stats(spark)
        counts["fact_player_contracts"] = build_fact_player_contracts(spark)
        counts["fact_player_injuries"] = build_fact_player_injuries(spark)
        counts["fact_player_shot_profiles"] = build_fact_player_shot_profiles(spark)
        counts["fact_team_results"] = build_fact_team_results(spark)
        counts["fact_player_profiles"] = build_fact_player_profiles(spark)
        counts["player_source_mapping"] = build_player_source_mapping(spark)
        run_quality_checks(spark)
    finally:
        stop_spark(spark)

    log.info(f"Bronze→Silver complete: {counts}")
    return counts


if __name__ == "__main__":
    run_all()
