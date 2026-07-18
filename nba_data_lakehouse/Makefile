.PHONY: help up down build logs status clean restart trigger-seed trigger-ingest trigger-bronze trigger-silver trigger-gold trigger-train trigger-score trigger-all ui-airflow ui-minio ui-mlflow ui-dashboard test lint

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Lifecycle ───────────────────────────────────────────────
env: ## Create .env from example if missing
	@test -f .env || cp .env.example .env && echo ".env ready"

up: env ## Start all services
	docker compose up --build -d

down: ## Stop all services
	docker compose down

build: ## Build all images
	docker compose build

logs: ## Tail all logs
	docker compose logs -f

status: ## Show service status
	docker compose ps

clean: ## Stop and remove all volumes
	docker compose down -v --remove-orphans

restart: down up ## Restart everything

# ── Airflow DAG triggers ────────────────────────────────────
trigger-seed: ## Trigger seed_local_sources DAG
	docker exec nba-airflow-scheduler airflow dags trigger seed_local_sources

trigger-ingest: ## Trigger ingest_sources_to_bronze DAG
	docker exec nba-airflow-scheduler airflow dags trigger ingest_sources_to_bronze

trigger-bronze: ## Trigger bronze_to_silver DAG
	docker exec nba-airflow-scheduler airflow dags trigger bronze_to_silver

trigger-silver: ## Trigger silver_to_gold DAG
	docker exec nba-airflow-scheduler airflow dags trigger silver_to_gold

trigger-gold: trigger-silver

trigger-train: ## Trigger train_models DAG
	docker exec nba-airflow-scheduler airflow dags trigger train_models

trigger-score: ## Trigger score_and_publish DAG
	docker exec nba-airflow-scheduler airflow dags trigger score_and_publish

trigger-all: ## Trigger full pipeline in order
	@echo "Triggering seed..."
	docker exec nba-airflow-scheduler airflow dags trigger seed_local_sources
	@echo "Wait for seed to complete, then trigger ingest..."
	@sleep 30
	docker exec nba-airflow-scheduler airflow dags trigger ingest_sources_to_bronze
	@sleep 60
	docker exec nba-airflow-scheduler airflow dags trigger bronze_to_silver
	@sleep 60
	docker exec nba-airflow-scheduler airflow dags trigger silver_to_gold
	@sleep 60
	docker exec nba-airflow-scheduler airflow dags trigger train_models
	@sleep 90
	docker exec nba-airflow-scheduler airflow dags trigger score_and_publish

# ── UI shortcuts ────────────────────────────────────────────
ui-airflow: ## Open Airflow UI
	open http://localhost:8080

ui-minio: ## Open MinIO console
	open http://localhost:9001

ui-mlflow: ## Open MLflow UI
	open http://localhost:5001

ui-dashboard: ## Open Streamlit dashboard
	open http://localhost:8501

# ── Development ─────────────────────────────────────────────
test: ## Run tests
	docker exec nba-airflow-scheduler python -m pytest /opt/airflow/tests/ -v

lint: ## Lint Python code
	python -m ruff check jobs/ dags/ apps/ tests/
