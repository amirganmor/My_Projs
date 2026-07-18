# Demo Walkthrough

## Quick Start

```bash
# 1. Pre-fetch real NBA data (requires internet, ~45-90 minutes)
pip install nba_api tqdm pandas requests
python scripts/fetch_real_nba_data.py --skip-existing

# 2. Start all services
cp .env.example .env
docker compose up --build -d

# 3. Trigger the full pipeline via Airflow UI or CLI
make trigger-all
```

## Service URLs

| Service | URL | Credentials |
|---------|-----|-------------|
| Airflow | http://localhost:8080 | admin / admin |
| MinIO | http://localhost:9001 | minioadmin / minioadmin123 |
| MLflow | http://localhost:5001 | — |
| Dashboard | http://localhost:8501 | — |
| Nessie | http://localhost:19120 | — |

## Pipeline Stages (in order)

### Stage 1: Seed Local Sources
- Loads salary CSV → PostgreSQL
- Loads scouting JSON → MongoDB
- Verifies all cached seed files are present

### Stage 2: Ingest Sources to Bronze
- Reads cached NBA API JSON → bronze Iceberg tables
- Reads advanced metrics CSV → bronze
- Reads historical bulk CSV → bronze
- Reads shot chart data → bronze
- Reads PostgreSQL tables → bronze
- Reads MongoDB collections → bronze

### Stage 3: Bronze → Silver
- Builds dim_players, dim_teams, dim_seasons
- Merges base stats + advanced metrics → fact_player_season_stats
- Creates fact tables for contracts, injuries, shot profiles
- Runs entity resolution with canonical IDs

### Stage 4: Silver → Gold
- Builds player_season_summary (cross-source analytics mart)
- Creates ML feature tables
- Builds data quality and source coverage summaries

### Stage 5: Train Models
- Trains 3 models for value prediction (Linear, RF, GBM)
- Trains 3 models for improvement prediction
- Logs all experiments to MLflow

### Stage 6: Score & Publish
- Scores underrated players
- Scores improvement candidates
- Builds trade target rankings
- Exports Parquet files to MinIO for dashboard

## YouTube Demo Script

1. Show `docker compose up --build` starting all 10+ containers
2. Open Airflow UI → show 6 DAGs
3. Trigger `seed_local_sources` → show PostgreSQL and MongoDB getting loaded
4. Trigger `ingest_sources_to_bronze` → show 6 source types flowing into bronze
5. Open MinIO → browse Iceberg warehouse files
6. Trigger `bronze_to_silver` → explain entity resolution and conformance
7. Trigger `silver_to_gold` → show cross-source feature tables
8. Trigger `train_models` → open MLflow to show experiment runs
9. Trigger `score_and_publish` → show scored outputs
10. Open Streamlit dashboard → walk through each page
11. Key message: "6 source families → 1 Iceberg lakehouse → 3 analytics outputs, all local"
