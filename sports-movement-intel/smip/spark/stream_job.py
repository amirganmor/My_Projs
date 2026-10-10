"""Spark Structured Streaming job: Kafka tracking frames -> bronze/silver/gold Iceberg + ClickHouse.

Query ``bronze``: every Kafka record (valid or not) is appended to bronze.kafka_tracking_raw with its
validation verdict; invalid records go to ops.quarantine, ClickHouse quarantine and the
``smip.quarantine.v1`` topic with an actionable reason.

Query ``engine``: valid records are grouped by (replay_session_id, match_id) and processed by the
shared ``MatchEngine`` through ``applyInPandasWithState``. The engine keeps its own per-match clock,
reorder buffer and dedup state, so one paused or slow replay never becomes "late" because another
match was accelerated (no global watermark is used for correctness). A processing-time timeout
finalizes idle matches.

Sink semantics (see docs/FAILURE_SEMANTICS.md):
* Iceberg: each append carries snapshot property ``smip.commit=<query>:<batch_id>``; on retry the job
  checks committed tags and skips tables already written for that batch (effectively exactly-once
  per table).
* ClickHouse: at-least-once inserts into ReplacingMergeTree tables with stable keys; reads use FINAL.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import pandas as pd

from smip.config import get_settings
from smip.spark.schemas import ENGINE_OUTPUT, ENGINE_STATE, ENVELOPE, KINDS
from smip.spark.session import build_spark
from smip.spark.tables import KIND_SINKS, ensure_tables

log = logging.getLogger("smip.stream")
TOPIC = "smip.tracking.v1"
QUARANTINE_TOPIC = "smip.quarantine.v1"


# ----------------------------------------------------------------- validation
def with_validation(df):
    """Adds parsed envelope ``e`` plus ``invalid_reason`` (null when valid). Spark built-ins only."""
    from pyspark.sql import functions as F

    e = F.from_json(F.col("value"), ENVELOPE, {"mode": "PERMISSIVE"})
    df = df.withColumn("e", e)
    eos = F.coalesce(F.col("e.end_of_stream"), F.lit(False))
    reason = (
        F.when(F.col("e").isNull() | F.col("e.match_id").isNull(), F.lit("unparseable_or_missing_match_id"))
        .when(F.col("e.replay_session_id").isNull(), F.lit("missing_replay_session_id"))
        .when(~F.coalesce(F.col("e.schema_version"), F.lit("")).startswith("1."), F.lit("unsupported_schema_version"))
        .when(F.col("e.record_type") != F.lit("tracking_frame"), F.lit("wrong_record_type"))
        .when(F.col("e.sequence").isNull() | (F.col("e.sequence") < 0), F.lit("bad_sequence"))
        .when(~eos & F.col("e.physical_time_ms").isNull(), F.lit("missing_physical_time"))
        .when(~eos & (F.col("e.physical_time_ms") < 0), F.lit("negative_physical_time"))
        .when(F.size(F.coalesce(F.col("e.players"), F.array())) > 40, F.lit("too_many_entities"))
        .when(F.col("key").isNotNull() & (F.col("key") != F.concat_ws("|", F.col("e.replay_session_id"),
                                                                        F.col("e.match_id"))),
              F.lit("key_envelope_mismatch"))
    )
    return df.withColumn("invalid_reason", reason)


def kafka_source(spark, name: str):
    s = get_settings()
    return (spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", s.kafka_bootstrap)
            .option("subscribe", TOPIC)
            .option("startingOffsets", "earliest")
            .option("maxOffsetsPerTrigger", os.environ.get("SMIP_MAX_OFFSETS", "6000"))
            .option("kafka.client.id", f"smip-{name}")
            .load()
            .selectExpr("CAST(key AS STRING) AS key", "CAST(value AS STRING) AS value", "topic",
                        "partition AS kafka_partition", "offset AS kafka_offset", "timestamp AS kafka_ts"))


# ------------------------------------------------------------ idempotent sink
class IcebergCommitLog:
    """Tracks ``smip.commit`` snapshot tags per table so retried batches are not appended twice."""

    def __init__(self, spark, query: str):
        self.spark, self.query, self.done = spark, query, {}

    def _load(self, table: str) -> set:
        if table not in self.done:
            try:
                rows = self.spark.sql(
                    f"SELECT summary['smip.commit'] AS c FROM smip.{table}.snapshots "
                    f"WHERE summary['smip.commit'] LIKE '{self.query}:%'").collect()
                self.done[table] = {r.c for r in rows}
            except Exception:  # table without snapshots yet
                self.done[table] = set()
        return self.done[table]

    def append(self, df, table: str, batch_id: int) -> bool:
        tag = f"{self.query}:{batch_id}"
        if tag in self._load(table):
            log.warning("skip %s batch %s: already committed (retry)", table, batch_id)
            return False
        df.writeTo(f"smip.{table}").option("snapshot-property.smip.commit", tag).append()
        self.done[table].add(tag)
        return True


def _ts(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def ch_insert(table: str, pdf: pd.DataFrame) -> int:
    from smip.serving import ch

    return ch.insert_df(table, pdf)


def ch_ledger(query: str, batch_id: int, sink: str, rows: int, t0: float) -> None:
    from smip.serving import ch

    ch.client().insert("sink_ledger", [[query, batch_id, sink, rows, datetime.now(timezone.utc),
                                        int((time.time() - t0) * 1000)]],
                       column_names=["query_name", "batch_id", "sink", "rows", "committed_at", "duration_ms"])


# -------------------------------------------------------------- bronze query
def bronze_batch(spark, commit: IcebergCommitLog):
    from pyspark.sql import functions as F

    def fn(batch_df, batch_id: int):
        t0 = time.time()
        df = with_validation(batch_df)
        # unparseable payloads are attributed through the Kafka key (session|match) so they stay traceable
        key_sid = F.when(F.instr("key", "|") > 0, F.substring_index("key", "|", 1))
        key_mid = F.when(F.instr("key", "|") > 0, F.expr("substring(key, instr(key, '|') + 1)"))
        df = df.withColumn("sid", F.coalesce(F.col("e.replay_session_id"), key_sid)) \
               .withColumn("mid", F.coalesce(F.col("e.match_id"), key_mid)) \
               .withColumn("attributed_by_key", F.col("e.match_id").isNull() & key_mid.isNotNull()).persist()
        out = df.select(
            "topic", "kafka_partition", "kafka_offset", "kafka_ts", "key", "value",
            F.col("sid").alias("replay_session_id"), F.col("mid").alias("match_id"),
            F.col("e.sequence").alias("sequence"), F.col("invalid_reason").isNull().alias("valid"),
            "invalid_reason", F.current_timestamp().alias("ingested_at"), F.lit(batch_id).cast("bigint").alias("batch_id"))
        n = out.count()
        commit.append(out, "bronze.kafka_tracking_raw", batch_id)
        bad = df.filter(F.col("invalid_reason").isNotNull())
        nbad = bad.count()
        if nbad:
            q = bad.select(
                F.current_timestamp().alias("detected_at"), F.col("sid").alias("session_id"),
                F.col("mid").alias("match_id"), F.col("e.sequence").alias("seq"),
                F.col("invalid_reason").alias("reason"),
                F.concat(F.lit("offset="), F.col("kafka_offset").cast("string"),
                         F.when(F.col("attributed_by_key"), F.lit(" session_from=kafka_key")).otherwise(F.lit(""))
                         ).alias("detail"),
                F.substring("value", 1, 4000).alias("raw_value"), "kafka_partition", "kafka_offset",
                F.lit(batch_id).cast("bigint").alias("batch_id"))
            commit.append(q, "ops.quarantine", batch_id)
            ch_insert("quarantine", _ch_frame(q.drop("kafka_partition", "kafka_offset").toPandas()))
            (q.select(F.col("session_id").alias("key"), F.to_json(F.struct("*")).alias("value"))
             .write.format("kafka").option("kafka.bootstrap.servers", get_settings().kafka_bootstrap)
             .option("topic", QUARANTINE_TOPIC).save())
        ch_ledger("bronze", batch_id, "bronze+quarantine", n, t0)
        df.unpersist()
        log.info("bronze batch %s rows=%s invalid=%s %.2fs", batch_id, n, nbad, time.time() - t0)

    return fn


# -------------------------------------------------------------- engine query
def engine_state_fn(key, pdf_iter, state):
    """applyInPandasWithState function: one MatchEngine per (session, match)."""
    from smip.features.context import context_from_meta, load_match_meta, sport_config
    from smip.features.engine import MatchEngine
    from smip.features.hooks import hooks_for

    session_id, match_id = key
    meta = load_match_meta(match_id)
    cfg = sport_config(meta["sport"])
    prev = json.loads(state.get[0]) if state.exists else None
    eng = MatchEngine(session_id, context_from_meta(meta), cfg, prev, frame_hooks=hooks_for(meta["sport"]))
    if state.hasTimedOut:
        if eng.ended:
            state.remove()
            return
        out = eng.finalize()
    else:
        msgs = []
        for pdf in pdf_iter:
            msgs.extend(json.loads(v) for v in pdf["value"])
        out = eng.ingest(msgs)
    state.update((json.dumps(eng.to_state(), separators=(",", ":")),))
    state.setTimeoutDuration(cfg.inactivity_timeout_ms if not eng.ended else 10 * 60 * 1000)
    rows = []
    for kind, recs in out.items():
        if kind == "stats":
            recs = recs[-1:]
        for r in recs:
            rows.append((session_id, match_id, kind, json.dumps(r, separators=(",", ":"))))
    if rows:
        yield pd.DataFrame(rows, columns=["session_id", "match_id", "kind", "payload"])


def engine_batch(spark, commit: IcebergCommitLog):
    from pyspark.sql import functions as F

    fv = _feature_version_col()
    schemas = {t: spark.table(f"smip.{t}").schema for t in
               [v[0] for v in KIND_SINKS.values()] + ["ops.quarantine", "ops.stream_stats"]}

    def conform(sdf, table):
        return sdf.select(*[F.col(f.name).cast(f.dataType).alias(f.name) for f in schemas[table].fields])

    def fn(batch_df, batch_id: int):
        t0 = time.time()
        if batch_df.isEmpty():  # timeout-only trigger with nothing emitted
            return
        df = batch_df.persist()
        total = 0
        for kind, (ice_table, ch_table, renames) in KIND_SINKS.items():
            sub = (df.filter(F.col("kind") == kind)
                   .select("session_id", "match_id", F.from_json("payload", KINDS[kind]).alias("p"))
                   .select("session_id", "match_id", "p.*"))
            for a, b in renames.items():
                sub = sub.withColumnRenamed(a, b)
            if kind == "obs":
                sub = sub.filter(F.col("x_m").isNotNull() & F.col("y_m").isNotNull())
            sub = sub.withColumn("batch_id", F.lit(batch_id).cast("bigint")).withColumn("feature_version", fv)
            if kind == "frame":
                sub = (sub.withColumn("processed_at", F.current_timestamp())
                       .withColumn("replay_event_time", F.to_timestamp("replay_event_time"))
                       .withColumn("produced_at", F.to_timestamp("produced_at")))
            ice = conform(sub, ice_table).persist()
            n = ice.count()
            if n == 0:
                ice.unpersist()
                continue
            commit.append(ice, ice_table, batch_id)
            from smip.serving import ch

            ch.insert_arrow(ch_table, ice.drop("feature_version").toArrow())
            ice.unpersist()
            total += n
        late = (df.filter(F.col("kind") == "late")
                .select("session_id", "match_id", F.from_json("payload", KINDS["late"]).alias("p"))
                .select(F.current_timestamp().alias("detected_at"), "session_id", "match_id",
                        F.col("p.seq").alias("seq"), F.col("p.reason").alias("reason"),
                        F.concat(F.lit("t_ms="), F.col("p.t").cast("string"), F.lit(" attempt="),
                                 F.col("p.attempt").cast("string")).alias("detail"),
                        F.lit("").alias("raw_value"), F.lit(None).alias("kafka_partition"),
                        F.lit(None).alias("kafka_offset"), F.lit(batch_id).alias("batch_id")))
        late = conform(late, "ops.quarantine").persist()
        if late.count():
            commit.append(late, "ops.quarantine", batch_id)
            ch_insert("quarantine", _ch_frame(late.drop("kafka_partition", "kafka_offset").toPandas()))
        late.unpersist()
        stats = conform(df.filter(F.col("kind") == "stats").select(
            "session_id", "match_id", F.current_timestamp().alias("emitted_at"),
            F.lit(batch_id).alias("batch_id"), F.col("payload").alias("stats")), "ops.stream_stats").persist()
        if stats.count():
            commit.append(stats, "ops.stream_stats", batch_id)
            ch_insert("stream_stats", stats.toPandas())
        stats.unpersist()
        ch_ledger("engine", batch_id, "silver+gold+clickhouse", total, t0)
        df.unpersist()
        log.info("engine batch %s rows=%s %.2fs", batch_id, total, time.time() - t0)

    return fn


def _feature_version_col():
    from pyspark.sql import functions as F

    from smip.features.context import sport_config
    from smip.features.engine import ENGINE_VERSION

    soccer = f"{sport_config('soccer').feature_version}+engine-{ENGINE_VERSION}"
    bball = f"{sport_config('basketball').feature_version}+engine-{ENGINE_VERSION}"
    return F.when(F.col("match_id").startswith("sportvu:"), F.lit(bball)).otherwise(F.lit(soccer))


def _ch_frame(pdf: pd.DataFrame) -> pd.DataFrame:
    for c in pdf.columns:
        if pdf[c].dtype == object:
            pdf[c] = pdf[c].where(pdf[c].notna(), None)
    return pdf


# ---------------------------------------------------------------------- main
def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("py4j").setLevel(logging.WARNING)
    from pyspark.sql import functions as F
    from pyspark.sql.streaming.state import GroupStateTimeout

    spark = build_spark("smip-stream")
    ensure_tables(spark)
    ckpt = os.environ.get("SMIP_SPARK_CHECKPOINT_DIR", str(get_settings().data_dir / "spark" / "checkpoints"))
    trigger = f"{os.environ.get('SMIP_TRIGGER_SECONDS', '2')} seconds"

    bronze = (kafka_source(spark, "bronze").writeStream.queryName("bronze")
              .foreachBatch(bronze_batch(spark, IcebergCommitLog(spark, "bronze")))
              .option("checkpointLocation", f"{ckpt}/bronze").trigger(processingTime=trigger).start())

    valid = (with_validation(kafka_source(spark, "engine"))
             .filter(F.col("invalid_reason").isNull())
             .select(F.col("e.replay_session_id").alias("session_id"), F.col("e.match_id").alias("match_id"),
                     "value"))
    engine = (valid.groupBy("session_id", "match_id")
              .applyInPandasWithState(engine_state_fn, ENGINE_OUTPUT, ENGINE_STATE, "append",
                                      GroupStateTimeout.ProcessingTimeTimeout)
              .writeStream.queryName("engine")
              .foreachBatch(engine_batch(spark, IcebergCommitLog(spark, "engine")))
              .option("checkpointLocation", f"{ckpt}/engine").trigger(processingTime=trigger).start())
    log.info("started queries: %s %s", bronze.id, engine.id)
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
