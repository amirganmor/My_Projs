"""
Spark Structured Streaming job: Kafka -> PostgreSQL.

Reads game data from all league Kafka topics, extracts scores, period scores,
and match events, then writes them to PostgreSQL tables via JDBC.
"""

import os
import logging
from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, explode, current_timestamp, size, when
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, ArrayType,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
TOPICS = "nba_scores,nfl_scores,premier_league_scores,la_liga_scores,champions_league_scores"

PG_URL = os.getenv("POSTGRES_URL", "jdbc:postgresql://postgres:5432/scoreboard")
PG_USER = os.getenv("POSTGRES_USER", "scoreboard")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "scoreboard")

spark = (
    SparkSession.builder
    .appName("MultiSport_Kafka_to_Postgres")
    .config("spark.sql.shuffle.partitions", "4")
    .getOrCreate()
)

period_schema = StructType([
    StructField("period", IntegerType()),
    StructField("homeScore", IntegerType()),
    StructField("awayScore", IntegerType()),
])

event_schema = StructType([
    StructField("type", StringType()),
    StructField("minute", IntegerType()),
    StructField("player", StringType()),
    StructField("playerIn", StringType()),
    StructField("playerOut", StringType()),
    StructField("team", StringType()),
])

game_schema = StructType([
    StructField("gameId", StringType()),
    StructField("statusText", StringType()),
    StructField("homeTeam", StructType([
        StructField("teamName", StringType()),
        StructField("score", IntegerType()),
    ])),
    StructField("awayTeam", StructType([
        StructField("teamName", StringType()),
        StructField("score", IntegerType()),
    ])),
    StructField("periods", ArrayType(period_schema)),
    StructField("events", ArrayType(event_schema)),
])

payload_schema = StructType([
    StructField("league", StringType()),
    StructField("games", ArrayType(game_schema)),
])

raw = (
    spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP)
    .option("subscribe", TOPICS)
    .option("startingOffsets", "latest")
    .load()
)

parsed = (
    raw.selectExpr("CAST(value AS STRING) as json_str")
    .select(from_json(col("json_str"), payload_schema).alias("data"))
    .select(col("data.league").alias("league"), explode(col("data.games")).alias("game"))
)


def pg_write(df, table, mode="append"):
    """Write a DataFrame to a PostgreSQL table via JDBC."""
    (
        df.write
        .format("jdbc")
        .option("url", PG_URL)
        .option("dbtable", table)
        .option("user", PG_USER)
        .option("password", PG_PASS)
        .option("driver", "org.postgresql.Driver")
        .mode(mode)
        .save()
    )


def pg_merge(df, target_table, staging_suffix="_staging"):
    """Write via staging table + INSERT ON CONFLICT DO NOTHING to prevent duplicates."""
    staging = f"{target_table}{staging_suffix}"
    pg_write(df, staging, mode="overwrite")

    conn = spark._jvm.java.sql.DriverManager.getConnection(PG_URL, PG_USER, PG_PASS)
    try:
        stmt = conn.createStatement()
        columns = ", ".join(df.columns)
        stmt.executeUpdate(
            f"INSERT INTO {target_table} ({columns}) "
            f"SELECT {columns} FROM {staging} "
            f"ON CONFLICT DO NOTHING"
        )
        stmt.executeUpdate(f"DROP TABLE IF EXISTS {staging}")
        stmt.close()
    finally:
        conn.close()


def write_batch(batch_df, batch_id):
    """Process a micro-batch: write scores, period scores, and match events to Postgres."""
    if batch_df.count() == 0:
        return

    batch_df.cache()

    try:
        scores_df = batch_df.select(
            col("league"),
            col("game.gameId").alias("game_id"),
            col("game.homeTeam.teamName").alias("home_team"),
            col("game.homeTeam.score").alias("home_score"),
            col("game.awayTeam.teamName").alias("away_team"),
            col("game.awayTeam.score").alias("away_score"),
            col("game.statusText").alias("status_text"),
            current_timestamp().alias("ingested_at"),
        )
        pg_merge(scores_df, "game_scores")
    except Exception as e:
        logger.error("Batch %s scores write error: %s", batch_id, e)

    try:
        has_periods = batch_df.filter(size(col("game.periods")) > 0)
        if has_periods.count() > 0:
            periods_df = (
                has_periods
                .select(col("league"), col("game.gameId").alias("game_id"), explode(col("game.periods")).alias("p"))
                .select(
                    col("league"),
                    col("game_id"),
                    col("p.period").alias("period_number"),
                    col("p.homeScore").alias("home_score"),
                    col("p.awayScore").alias("away_score"),
                    current_timestamp().alias("ingested_at"),
                )
            )
            pg_merge(periods_df, "period_scores")
    except Exception as e:
        logger.error("Batch %s periods write error: %s", batch_id, e)

    try:
        has_events = batch_df.filter(size(col("game.events")) > 0)
        if has_events.count() > 0:
            events_df = (
                has_events
                .select(col("league"), col("game.gameId").alias("game_id"), explode(col("game.events")).alias("e"))
                .select(
                    col("league"),
                    col("game_id"),
                    col("e.type").alias("event_type"),
                    col("e.minute").alias("minute"),
                    when(col("e.type") == "substitution", None).otherwise(col("e.player")).alias("player_name"),
                    when(col("e.type") == "substitution", col("e.playerIn")).alias("player_in"),
                    when(col("e.type") == "substitution", col("e.playerOut")).alias("player_out"),
                    col("e.team").alias("team"),
                    current_timestamp().alias("ingested_at"),
                )
            )
            pg_merge(events_df, "match_events")
    except Exception as e:
        logger.error("Batch %s events write error: %s", batch_id, e)

    batch_df.unpersist()


query = (
    parsed.writeStream
    .foreachBatch(write_batch)
    .outputMode("append")
    .trigger(processingTime="10 seconds")
    .option("checkpointLocation", "/tmp/spark_checkpoint/scoreboard_v2")
    .start()
)

query.awaitTermination()
