"""SparkSession factory with the Iceberg REST catalog (``smip``) on the S3-compatible object store."""

from __future__ import annotations

import os

from smip.config import get_settings


def build_spark(app_name: str, master: str | None = None, extra: dict | None = None):
    from pyspark.sql import SparkSession

    s = get_settings()
    b = SparkSession.builder.appName(app_name)
    if master or os.environ.get("SMIP_SPARK_MASTER"):
        b = b.master(master or os.environ["SMIP_SPARK_MASTER"])
    conf = {
        "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        "spark.sql.catalog.smip": "org.apache.iceberg.spark.SparkCatalog",
        "spark.sql.catalog.smip.type": "rest",
        "spark.sql.catalog.smip.uri": s.iceberg_rest_uri,
        "spark.sql.catalog.smip.warehouse": s.warehouse,
        "spark.sql.catalog.smip.io-impl": "org.apache.iceberg.aws.s3.S3FileIO",
        "spark.sql.catalog.smip.s3.endpoint": s.s3_endpoint,
        "spark.sql.catalog.smip.s3.path-style-access": "true",
        "spark.sql.catalog.smip.s3.access-key-id": s.s3_access_key,
        "spark.sql.catalog.smip.s3.secret-access-key": s.s3_secret_key,
        "spark.sql.catalog.smip.client.region": s.s3_region,
        "spark.sql.defaultCatalog": "smip",
        "spark.sql.session.timeZone": "UTC",
        "spark.sql.execution.arrow.pyspark.enabled": "true",
        "spark.sql.streaming.stateStore.providerClass":
            "org.apache.spark.sql.execution.streaming.state.RocksDBStateStoreProvider",
        "spark.ui.showConsoleProgress": "false",
    }
    jars = os.environ.get("SMIP_SPARK_JARS")
    if jars:
        conf["spark.jars"] = jars
    conf.update(extra or {})
    for k, v in conf.items():
        b = b.config(k, v)
    spark = b.getOrCreate()
    spark.sparkContext.setLogLevel(os.environ.get("SMIP_SPARK_LOG_LEVEL", "WARN"))
    return spark
