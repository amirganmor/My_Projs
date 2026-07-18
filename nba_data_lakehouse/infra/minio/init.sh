#!/bin/sh
set -e

echo "Waiting for MinIO to be ready..."
until mc alias set myminio http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" 2>/dev/null; do
    sleep 2
done

echo "Creating buckets..."
mc mb --ignore-existing myminio/nba-lakehouse

# Create prefixes for the lakehouse
mc put /dev/null myminio/nba-lakehouse/iceberg-warehouse/.keep 2>/dev/null || true
mc put /dev/null myminio/nba-lakehouse/mlflow-artifacts/.keep 2>/dev/null || true
mc put /dev/null myminio/nba-lakehouse/seed-data/.keep 2>/dev/null || true
mc put /dev/null myminio/nba-lakehouse/exports/.keep 2>/dev/null || true

# Upload seed data files to MinIO
if [ -d /seed_data/files ]; then
    echo "Uploading seed data files to MinIO..."
    mc cp --recursive /seed_data/files/ myminio/nba-lakehouse/seed-data/files/ 2>/dev/null || true
fi

if [ -d /seed_data/api_mock ]; then
    echo "Uploading API mock data to MinIO..."
    mc cp --recursive /seed_data/api_mock/ myminio/nba-lakehouse/seed-data/api_mock/ 2>/dev/null || true
fi

echo "MinIO initialization complete."
