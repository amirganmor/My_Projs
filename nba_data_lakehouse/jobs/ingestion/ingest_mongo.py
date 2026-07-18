"""
Ingest MongoDB collections into Bronze Iceberg tables.

Source Family 6: Scouting reports and player profiles (nested documents).
Tables: bronze.mongo_player_profiles, bronze.mongo_scouting_reports
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.mongo_utils import read_collection
from jobs.common.schemas import BRONZE_TABLES
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("ingest.mongo")


def _add_metadata(df: DataFrame, source_name: str, batch_id: str) -> DataFrame:
    return (
        df
        .withColumn("ingestion_ts", F.current_timestamp())
        .withColumn("source_name", F.lit(source_name))
        .withColumn("batch_id", F.lit(batch_id))
    )


def _flatten_nested_to_json_strings(docs: list[dict]) -> list[dict]:
    """Convert nested dicts/lists to JSON strings for Iceberg compatibility."""
    flat_docs = []
    for doc in docs:
        flat = {}
        for k, v in doc.items():
            if isinstance(v, (dict, list)):
                flat[k] = json.dumps(v, default=str)
            else:
                flat[k] = v
        flat_docs.append(flat)
    return flat_docs


def ingest_player_profiles(spark: SparkSession, batch_id: str) -> int:
    log.info("Ingesting player profiles from MongoDB...")
    try:
        docs = read_collection("player_profiles")
    except Exception as e:
        log.warning(f"  Failed to read from MongoDB, falling back to JSON file: {e}")
        cfg = get_config()
        json_path = cfg.mongo_seed_path / "player_profiles.json"
        if json_path.exists():
            with open(json_path) as f:
                docs = json.load(f)
        else:
            return 0

    if not docs:
        log.warning("  No player profile documents found")
        return 0

    flat_docs = _flatten_nested_to_json_strings(docs)
    df = spark.createDataFrame(flat_docs)
    df = _add_metadata(df, "mongo_profiles", batch_id)
    df.writeTo(BRONZE_TABLES["mongo_player_profiles"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  bronze.mongo_player_profiles: {count:,} rows")
    return count


def ingest_scouting_reports(spark: SparkSession, batch_id: str) -> int:
    log.info("Ingesting scouting reports from MongoDB...")
    try:
        docs = read_collection("scouting_reports")
    except Exception as e:
        log.warning(f"  Failed to read from MongoDB, falling back to JSON file: {e}")
        cfg = get_config()
        json_path = cfg.mongo_seed_path / "scouting_reports.json"
        if json_path.exists():
            with open(json_path) as f:
                docs = json.load(f)
        else:
            return 0

    if not docs:
        log.warning("  No scouting report documents found")
        return 0

    flat_docs = _flatten_nested_to_json_strings(docs)
    df = spark.createDataFrame(flat_docs)
    df = _add_metadata(df, "mongo_scouting", batch_id)
    df.writeTo(BRONZE_TABLES["mongo_scouting_reports"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  bronze.mongo_scouting_reports: {count:,} rows")
    return count


def run_all() -> dict[str, int]:
    spark = get_spark("ingest_mongo")
    batch_id = f"mongo_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    try:
        spark.sql("CREATE NAMESPACE IF NOT EXISTS nessie.bronze")
    except Exception:
        pass

    counts = {}
    try:
        counts["player_profiles"] = ingest_player_profiles(spark, batch_id)
        counts["scouting_reports"] = ingest_scouting_reports(spark, batch_id)
    finally:
        stop_spark(spark)

    log.info(f"MongoDB ingestion complete: {counts}")
    return counts


if __name__ == "__main__":
    run_all()
