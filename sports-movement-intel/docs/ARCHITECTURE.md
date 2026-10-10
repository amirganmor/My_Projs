# Architecture

Every replay here is a **historical match replay** of public tracking data. There is no live feed.

![Architecture](img/architecture.png)

The source for this image is [diagrams/architecture.html](diagrams/architecture.html). Re-render it with `make diagram`.
An animated, clickable version (replay speed, fault injection, component inspector) is in
[diagrams/architecture-live.html](diagrams/architecture-live.html). Open it in a browser.

```mermaid
flowchart LR
  subgraph Sources["Public sources (pinned revisions)"]
    SC["SkillCorner open data<br/>10 Hz · MIT"]
    ME["Metrica sample<br/>25 Hz · local only"]
    SV["NBA SportVU 2015-16<br/>25 Hz · local only"]
  end
  subgraph Acquire["smip sources"]
    DL["download + sha256<br/>safe extract"] --> NORM["adapters → canonical parquet<br/>data/normalized/&lt;source&gt;/&lt;match&gt;"]
    NORM --> CAT["catalog<br/>manifest.lock.json · DATA_SOURCES.md"]
  end
  subgraph Replay["replay service"]
    RP["deterministic replay<br/>speed 0.5–100× · seeded faults"]
  end
  subgraph Kafka["Kafka 4.3 (KRaft)"]
    T1["smip.tracking.v1<br/>key = session|match"]
    TQ["smip.quarantine.v1"]
  end
  subgraph Spark["Spark 4.1 Structured Streaming"]
    BZ["bronze query<br/>validate · quarantine"]
    EN["engine query<br/>applyInPandasWithState<br/>reorder · dedup · windows"]
  end
  subgraph Lake["Iceberg 1.11 · REST catalog · S3 gateway"]
    B["bronze.kafka_tracking_raw"]
    S["silver.tracking_frames / positions"]
    G["gold.player_windows · team_windows<br/>team_frame_metrics · spatial_dwell"]
    O["ops.quarantine · ops.stream_stats"]
  end
  CH["ClickHouse 25.8<br/>ReplacingMergeTree"]
  API["FastAPI<br/>frames · metrics · ML · analyst"]
  UI["React dashboard<br/>Canvas + SVG"]
  Sources --> DL
  NORM --> RP --> T1
  T1 --> BZ --> B & O
  BZ --> TQ
  T1 --> EN --> S & G & O
  EN --> CH
  BZ --> CH
  CH --> API --> UI
  G -. lineage .-> API
```

## Components

| layer | what it does | where |
|---|---|---|
| acquisition | resumable download, checksums, zip/7z extraction with path and size guards, license registry | `smip/sources/` |
| adapters | SkillCorner, Metrica, SportVU → one canonical contract (meters, centre origin, attack-normalized copy) | `smip/sources/adapters/` |
| replay | re-emits normalized frames through Kafka on a replay clock; seeded, bounded faults | `smip/replay/` |
| bronze query | parses every Kafka record, validates the envelope, writes bronze + quarantine | `smip/spark/stream_job.py` |
| engine query | per `(session, match)` state: reorder buffer, dedup, corrections, kinematics, windows | `smip/features/engine.py` |
| batch engine | the same engine class over normalized parquet, used for parity | `smip/features/batch.py` |
| lakehouse | Iceberg tables as plain files under `./lakehouse/data/warehouse` | `smip/spark/tables.py`, `smip/lakehouse.py` |
| serving | ClickHouse tables read with `FINAL`; FastAPI endpoints | `sql/clickhouse/`, `smip/serving/` |
| ML | similar moments (kNN), shape change points (PELT) | `smip/ml/` |
| analyst | deterministic router over five typed read-only tools | `smip/analyst/` |
| orchestration | optional Airflow profile: `smip_data`, `smip_quality` DAGs | `dags/`, compose profile `orchestration` |

## One engine, two runtimes

`FeatureEngine` is plain Python/numpy. The stream job wraps it in `applyInPandasWithState` keyed by
`(replay_session_id, match_id)`; the batch job feeds it the normalized parquet directly. `smip batch parity`
compares final windows from both paths row by row. The demo sessions pass with zero differences
(see `docs/STATUS.md`).

## Resource envelope

Everything runs in one Compose file on a 7.65 GiB Docker VM. Memory limits are set per container
(Spark 2300m, ClickHouse 1800m, Kafka 900m, API 700m, …). Airflow is behind the `orchestration`
profile because the full stack plus Airflow does not fit; its DAGs were verified with `spark-stream` stopped.

## Ports (all bound to 127.0.0.1)

| service | port |
|---|---|
| API + dashboard | 18000 |
| ClickHouse HTTP | 18123 |
| Kafka (host listener) | 19092 |
| Iceberg REST | 18181 |
| S3 gateway / web UI | 17070 / 17071 |
| Spark UI | 14040 |
| Airflow (profile) | 18080 |
