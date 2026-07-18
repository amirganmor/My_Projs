#!/bin/bash
# Bootstrap script: copy .env, build, and start everything
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

echo "Building and starting all services..."
docker compose up --build -d

echo ""
echo "============================================"
echo "  NBA Athlete Performance Lakehouse"
echo "============================================"
echo ""
echo "Services starting up. Give them ~60 seconds."
echo ""
echo "  Airflow UI:      http://localhost:8080  (admin/admin)"
echo "  MinIO Console:   http://localhost:9001  (minioadmin/minioadmin123)"
echo "  MLflow UI:       http://localhost:5001"
echo "  Dashboard:       http://localhost:8501"
echo "  Nessie API:      http://localhost:19120"
echo ""
echo "Trigger the full pipeline:"
echo "  make trigger-all"
echo ""
