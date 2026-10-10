SHELL := /bin/bash
PY ?= .venv/bin/python
SMIP ?= .venv/bin/smip
COMPOSE ?= docker compose
PROFILE ?= sample
MATCH ?= skillcorner:1886347
SESSION ?= demo-soccer-hero
SPEED ?= 20

.PHONY: help setup doctor sources-list sources-download sources-verify sources-normalize catalog data \
        ui build up up-ai down reset logs ps replay replay-faults parity test lint \
        iceberg-inspect ml-eval analyst-eval bench screenshots diagram verify demo demo-seed airflow

help:
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-20s %s\n", $$1, $$2}'

setup: ## create .venv with all extras
	uv venv --python 3.12 .venv && uv pip install --python $(PY) -e '.[app,ml,ai,nba,dev]'
	[ -f .env ] || cp .env.example .env

doctor: ## environment and stack checks
	$(SMIP) doctor

sources-list: ## registered sources with license/access status
	$(SMIP) sources list

sources-download: ## resumable download of PROFILE (sample|research|full)
	$(SMIP) sources download --profile $(PROFILE)

sources-verify: ## re-hash all raw assets
	$(SMIP) sources verify

sources-normalize: ## raw -> canonical parquet contracts
	$(SMIP) sources normalize

catalog: ## rebuild manifest lock and docs/DATA_SOURCES.md
	$(SMIP) sources catalog

data: sources-download sources-verify sources-normalize catalog ## full acquisition pipeline

ui: ## build the React dashboard (served by the API container)
	cd frontend && npm ci && npm run build

build: ## build all images
	$(COMPOSE) build

up: ## start the core stack
	mkdir -p lakehouse/data/warehouse lakehouse/.meta lakehouse/catalog data/spark
	$(COMPOSE) up -d --wait

up-ai: ## core stack + MLflow UI + Qdrant
	$(COMPOSE) --profile ai up -d --wait

down: ## stop containers (keeps data)
	$(COMPOSE) --profile ai --profile orchestration down

reset: ## stop and delete stream state, lakehouse and ClickHouse volume (keeps raw data)
	$(COMPOSE) --profile ai --profile orchestration down -v
	rm -rf lakehouse data/spark data/state data/demo

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100 spark-stream replay api

replay: ## historical replay of MATCH at SPEED through Kafka
	$(SMIP) replay start --match $(MATCH) --speed $(SPEED)

replay-faults: ## replay with duplicate/delay/out-of-order/drop/correction/malformed faults
	$(SMIP) replay start --match $(MATCH) --speed 0 --dup 0.02 --delay 0.02 --ooo 0.02 --drop 0.005 --corr 0.01 --malformed 0.002

parity: ## compare batch vs stream final windows for SESSION
	$(SMIP) batch parity --match $(MATCH) --session $(SESSION)

iceberg-inspect: ## list Iceberg tables, snapshots and files under ./lakehouse
	$(SMIP) lakehouse inspect

ml-eval: ## similar-moments lift + change points for the three demo sessions
	$(SMIP) ml eval --session demo-soccer-hero --match skillcorner:1886347
	$(SMIP) ml eval --session demo-soccer-faults --match skillcorner:1874553
	$(SMIP) ml eval --session demo-nba --match sportvu:0021500492

analyst-eval: ## grounded analyst evaluation set
	$(SMIP) analyst eval

bench: ## measured throughput / latency / memory -> docs/BENCHMARKS.md
	$(SMIP) bench run --match $(MATCH)

screenshots: ## headless screenshots of every view -> docs/img (stack + demo seed required)
	cd frontend && node scripts/screenshots.mjs

diagram: ## render docs/diagrams/architecture.html -> docs/img/architecture.png
	cd frontend && node scripts/diagram.mjs

verify: ## end-to-end gate: tests, health, parity x3, lineage, fault counters, analyst eval, UI build
	$(PY) -m smip.verify

test: ## unit tests (synthetic fixtures) + integration tests if stack is up
	$(PY) -m pytest -q

lint: ## ruff
	.venv/bin/ruff check smip tests dags

demo-seed: ## replay hero/faults/NBA demo sessions and verify parity + lineage
	$(SMIP) demo seed

airflow: ## optional orchestration profile (stop spark-stream first on 8 GiB Docker VMs)
	$(COMPOSE) --profile orchestration up -d --wait airflow

demo: up demo-seed ## bring up the stack and seed the demo sessions
	@echo "open http://127.0.0.1:18000"
