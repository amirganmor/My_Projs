# Architecture

## System Overview

The NBA Athlete Performance Lakehouse is a fully local/on-prem analytics platform that merges 6 heterogeneous NBA data source families into a unified Apache Iceberg lakehouse.

## Component Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Object Storage | MinIO | S3-compatible store for Iceberg data files, model artifacts, exports |
| Iceberg Catalog | Nessie | Version-controlled lakehouse metadata |
| Orchestration | Apache Airflow | DAG-based pipeline execution |
| Compute | PySpark (embedded) | Iceberg read/write, transformations |
| SQL Source | PostgreSQL | Contracts, injuries, rosters + Airflow/MLflow metadata |
| NoSQL Source | MongoDB | Scouting reports, player profiles |
| ML Tracking | MLflow | Experiment logging, model registry |
| Dashboard | Streamlit | Interactive analytics visualization |

## Data Flow

```
Source Systems                 Orchestration              Lakehouse               Analytics
─────────────                 ──────────────             ──────────              ──────────
NBA API (JSON)    ──┐
Advanced CSV      ──┤
Historical CSV    ──┼── Airflow DAGs ──→ Bronze (Iceberg) ──→ Silver ──→ Gold ──→ ML Training
Shot Charts       ──┤       │                                                      │
PostgreSQL        ──┤       │                                                    MLflow
MongoDB           ──┘       │                                                      │
                            └── Scoring ──→ Scored Outputs (Gold) ──→ Dashboard + Exports
```

## Medallion Architecture

### Bronze Layer
- Source-shaped raw data, one table per source feed
- Preserves original schema with metadata columns (ingestion_ts, source_name, batch_id)
- 17 tables across 6 source families

### Silver Layer
- Conformed dimensions (players, teams, seasons, games)
- Standardized facts (player stats, contracts, injuries, shot profiles)
- Entity resolution with canonical IDs
- 12 tables

### Gold Layer
- Analytics marts (player season summary, value vs salary)
- ML feature tables (value model, improvement model, trade target features)
- Scored outputs (underrated players, improvement candidates, trade targets)
- Data quality and source coverage summaries
- 12 tables
