"""
Ingest file-based sources (CSV / JSON) into Bronze Iceberg tables.

Source Family 2: Advanced Metrics  (CSV per season)
Source Family 3: Historical Bulk   (large consolidated CSVs)
Source Family 4: Shot Charts       (CSV zone summaries + JSON shot details)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.schemas import BRONZE_TABLES
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("ingest.files")


def _add_metadata(df: DataFrame, source_name: str, batch_id: str, filename: str = "") -> DataFrame:
    return (
        df
        .withColumn("ingestion_ts", F.current_timestamp())
        .withColumn("source_name", F.lit(source_name))
        .withColumn("batch_id", F.lit(batch_id))
        .withColumn("raw_file_name", F.lit(filename))
    )


def _create_namespace_if_needed(spark: SparkSession, ns: str) -> None:
    try:
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {ns}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Source 2: Advanced Metrics
# ---------------------------------------------------------------------------

def ingest_advanced_metrics(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    adv_dir = cfg.files_path / "advanced_metrics"
    if not adv_dir.exists():
        log.warning("advanced_metrics directory not found")
        return 0

    csv_files = sorted(adv_dir.glob("advanced_stats_*.csv"))
    if not csv_files:
        log.warning("No advanced metrics CSV files found")
        return 0

    total = 0
    table = BRONZE_TABLES["advanced_player_metrics"]
    first = True

    for csv_file in csv_files:
        season = csv_file.stem.replace("advanced_stats_", "")
        df = spark.read.option("header", "true").option("inferSchema", "true").csv(str(csv_file))
        df = _add_metadata(df, "advanced_metrics", batch_id, csv_file.name)
        df = df.withColumn("season", F.lit(season))
        count = df.count()
        total += count

        if first:
            df.writeTo(table).using("iceberg").createOrReplace()
            first = False
        else:
            df.writeTo(table).using("iceberg").append()

        log.info(f"  Advanced {season}: {count:,} rows")

    log.info(f"  Total advanced metrics: {total:,}")
    return total


# ---------------------------------------------------------------------------
# Source 3: Historical Bulk
# ---------------------------------------------------------------------------

def ingest_historical_player_seasons(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    path = cfg.files_path / "historical" / "historical_player_seasons.csv"
    if not path.exists():
        log.warning("historical_player_seasons.csv not found")
        return 0

    df = spark.read.option("header", "true").option("inferSchema", "true").csv(str(path))
    df = _add_metadata(df, "historical_bulk", batch_id, path.name)
    df.writeTo(BRONZE_TABLES["historical_player_seasons"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  Historical player seasons: {count:,}")
    return count


def ingest_historical_box_scores(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    path = cfg.files_path / "historical" / "historical_box_scores.csv"
    if not path.exists():
        log.warning("historical_box_scores.csv not found")
        return 0

    df = spark.read.option("header", "true").option("inferSchema", "true").csv(str(path))
    df = _add_metadata(df, "historical_bulk", batch_id, path.name)
    df.writeTo(BRONZE_TABLES["historical_box_scores"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  Historical box scores: {count:,}")
    return count


def ingest_historical_standings(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    path = cfg.files_path / "historical" / "historical_team_standings.csv"
    if not path.exists():
        log.warning("historical_team_standings.csv not found")
        return 0

    df = spark.read.option("header", "true").option("inferSchema", "true").csv(str(path))
    df = _add_metadata(df, "historical_bulk", batch_id, path.name)
    df.writeTo(BRONZE_TABLES["historical_team_standings"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  Historical team standings: {count:,}")
    return count


# ---------------------------------------------------------------------------
# Source 4: Shot Charts
# ---------------------------------------------------------------------------

def ingest_shot_zones(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    shot_dir = cfg.files_path / "shot_charts"
    if not shot_dir.exists():
        return 0

    csv_files = sorted(shot_dir.glob("shot_zones_*.csv"))
    if not csv_files:
        log.warning("No shot zone CSV files found")
        return 0

    total = 0
    table = BRONZE_TABLES["shot_chart_zones"]
    first = True

    for csv_file in csv_files:
        season = csv_file.stem.replace("shot_zones_", "")
        df = spark.read.option("header", "true").option("inferSchema", "true").csv(str(csv_file))
        df = _add_metadata(df, "shot_charts", batch_id, csv_file.name)
        if "SEASON" not in df.columns:
            df = df.withColumn("SEASON", F.lit(season))
        count = df.count()
        total += count

        if first:
            df.writeTo(table).using("iceberg").createOrReplace()
            first = False
        else:
            df.writeTo(table).using("iceberg").append()

        log.info(f"  Shot zones {season}: {count:,} rows")

    log.info(f"  Total shot zones: {total:,}")
    return total


def ingest_shot_details(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    shot_dir = cfg.files_path / "shot_charts"
    if not shot_dir.exists():
        return 0

    json_files = sorted(shot_dir.glob("shot_detail_*.json"))
    if not json_files:
        log.info("No shot detail JSON files found (optional)")
        return 0

    total = 0
    table = BRONZE_TABLES["shot_chart_details"]
    first = True

    for json_file in json_files:
        season = json_file.stem.replace("shot_detail_", "")
        df = spark.read.option("multiline", "true").json(str(json_file))
        df = _add_metadata(df, "shot_charts", batch_id, json_file.name)
        if "SEASON" not in [c.upper() for c in df.columns]:
            df = df.withColumn("SEASON", F.lit(season))
        count = df.count()
        total += count

        if first:
            df.writeTo(table).using("iceberg").createOrReplace()
            first = False
        else:
            df.writeTo(table).using("iceberg").append()

        log.info(f"  Shot detail {season}: {count:,} rows")

    log.info(f"  Total shot details: {total:,}")
    return total


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_all() -> dict[str, int]:
    spark = get_spark("ingest_files")
    batch_id = f"files_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    _create_namespace_if_needed(spark, "nessie.bronze")

    counts = {}
    try:
        counts["advanced_metrics"] = ingest_advanced_metrics(spark, batch_id)
        counts["hist_player_seasons"] = ingest_historical_player_seasons(spark, batch_id)
        counts["hist_box_scores"] = ingest_historical_box_scores(spark, batch_id)
        counts["hist_standings"] = ingest_historical_standings(spark, batch_id)
        counts["shot_zones"] = ingest_shot_zones(spark, batch_id)
        counts["shot_details"] = ingest_shot_details(spark, batch_id)
    finally:
        stop_spark(spark)

    log.info(f"File ingestion complete: {counts}")
    return counts


if __name__ == "__main__":
    run_all()
