"""
Ingest PostgreSQL source tables into Bronze Iceberg tables.

Source Family 5: Salary / contract, injury, and roster data.
Tables: bronze.contracts, bronze.injuries, bronze.rosters
"""
from __future__ import annotations

from datetime import datetime

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.schemas import BRONZE_TABLES
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("ingest.postgres")


def _add_metadata(df: DataFrame, source_name: str, batch_id: str) -> DataFrame:
    return (
        df
        .withColumn("ingestion_ts", F.current_timestamp())
        .withColumn("source_name", F.lit(source_name))
        .withColumn("batch_id", F.lit(batch_id))
    )


def _read_postgres_table(spark: SparkSession, table: str) -> DataFrame:
    cfg = get_config().postgres
    return (
        spark.read
        .format("jdbc")
        .option("url", cfg.jdbc_url)
        .option("dbtable", table)
        .option("user", cfg.user)
        .option("password", cfg.password)
        .option("driver", "org.postgresql.Driver")
        .load()
    )


def ingest_contracts(spark: SparkSession, batch_id: str) -> int:
    log.info("Ingesting contracts from PostgreSQL...")
    try:
        df = _read_postgres_table(spark, "contracts")
    except Exception as e:
        log.warning(f"  Failed to read contracts (may need JDBC driver): {e}")
        # Fallback: read from CSV directly
        cfg = get_config()
        csv_path = str(cfg.postgres_seed_path / "contracts.csv")
        df = spark.read.option("header", "true").option("inferSchema", "true").csv(csv_path)

    df = _add_metadata(df, "postgres_contracts", batch_id)
    df.writeTo(BRONZE_TABLES["contracts"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  bronze.contracts: {count:,} rows")
    return count


def ingest_injuries(spark: SparkSession, batch_id: str) -> int:
    log.info("Ingesting injuries from PostgreSQL...")
    try:
        df = _read_postgres_table(spark, "injuries")
    except Exception:
        cfg = get_config()
        csv_path = str(cfg.postgres_seed_path / "injuries.csv")
        df = spark.read.option("header", "true").option("inferSchema", "true").csv(csv_path)

    df = _add_metadata(df, "postgres_injuries", batch_id)
    df.writeTo(BRONZE_TABLES["injuries"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  bronze.injuries: {count:,} rows")
    return count


def ingest_rosters(spark: SparkSession, batch_id: str) -> int:
    log.info("Ingesting rosters from PostgreSQL...")
    try:
        df = _read_postgres_table(spark, "rosters")
    except Exception:
        cfg = get_config()
        csv_path = str(cfg.postgres_seed_path / "rosters.csv")
        df = spark.read.option("header", "true").option("inferSchema", "true").csv(csv_path)

    df = _add_metadata(df, "postgres_rosters", batch_id)
    df.writeTo(BRONZE_TABLES["rosters"]).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  bronze.rosters: {count:,} rows")
    return count


def run_all() -> dict[str, int]:
    spark = get_spark("ingest_postgres")
    batch_id = f"pg_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    try:
        spark.sql("CREATE NAMESPACE IF NOT EXISTS nessie.bronze")
    except Exception:
        pass

    counts = {}
    try:
        counts["contracts"] = ingest_contracts(spark, batch_id)
        counts["injuries"] = ingest_injuries(spark, batch_id)
        counts["rosters"] = ingest_rosters(spark, batch_id)
    finally:
        stop_spark(spark)

    log.info(f"Postgres ingestion complete: {counts}")
    return counts


if __name__ == "__main__":
    run_all()
