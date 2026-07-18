"""
Build a PySpark session wired to Nessie + Iceberg + MinIO (S3A).
"""
from __future__ import annotations

import os

import pyspark
# Force SPARK_HOME to the actual pyspark package directory — the container
# env may inherit a stale value pointing to a path without bin/spark-submit.
os.environ["SPARK_HOME"] = os.path.dirname(pyspark.__file__)

from pyspark.sql import SparkSession

from jobs.common.config import get_config

SPARK_JARS_DIR = os.environ.get("SPARK_JARS_DIR", "/opt/spark-jars")


def get_spark(app_name: str = "nba_lakehouse") -> SparkSession:
    """Return a SparkSession configured for Iceberg via Nessie + MinIO."""
    cfg = get_config()

    jar_files = ",".join([
        f"{SPARK_JARS_DIR}/iceberg-spark-runtime.jar",
        f"{SPARK_JARS_DIR}/iceberg-aws-bundle.jar",
        f"{SPARK_JARS_DIR}/nessie-spark-extensions.jar",
        f"{SPARK_JARS_DIR}/hadoop-aws.jar",
        f"{SPARK_JARS_DIR}/aws-java-sdk-bundle.jar",
        f"{SPARK_JARS_DIR}/postgresql-jdbc.jar",
    ])

    builder = (
        SparkSession.builder
        .appName(app_name)
        .config("spark.jars", jar_files)
        # Iceberg + Nessie catalog
        .config("spark.sql.extensions",
                "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,"
                "org.projectnessie.spark.extensions.NessieSparkSessionExtensions")
        .config("spark.sql.catalog.nessie", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.nessie.catalog-impl", "org.apache.iceberg.nessie.NessieCatalog")
        .config("spark.sql.catalog.nessie.uri", cfg.nessie.uri)
        .config("spark.sql.catalog.nessie.ref", "main")
        .config("spark.sql.catalog.nessie.authentication.type", "NONE")
        .config("spark.sql.catalog.nessie.warehouse", cfg.iceberg.warehouse)
        .config("spark.sql.catalog.nessie.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
        .config("spark.sql.catalog.nessie.s3.endpoint", cfg.minio.endpoint)
        .config("spark.sql.catalog.nessie.s3.path-style-access", "true")
        .config("spark.sql.catalog.nessie.s3.access-key-id", cfg.minio.access_key)
        .config("spark.sql.catalog.nessie.s3.secret-access-key", cfg.minio.secret_key)
        # S3A / Hadoop config for MinIO
        .config("spark.hadoop.fs.s3a.endpoint", cfg.minio.endpoint)
        .config("spark.hadoop.fs.s3a.access.key", cfg.minio.access_key)
        .config("spark.hadoop.fs.s3a.secret.key", cfg.minio.secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        # Performance
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.catalog.nessie.cache-enabled", "false")
        .config("spark.driver.memory", "2g")
    )

    return builder.getOrCreate()


def stop_spark(spark: SparkSession) -> None:
    spark.stop()
