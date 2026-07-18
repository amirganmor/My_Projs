#!/bin/bash
set -e

wait_for_port() {
    local host=$1 port=$2 name=$3 retries=${4:-30}
    echo "Waiting for $name ($host:$port)..."
    for i in $(seq 1 $retries); do
        if nc -z "$host" "$port" 2>/dev/null; then
            echo "  $name is ready."
            return 0
        fi
        sleep 2
    done
    echo "  ERROR: $name did not become ready in time."
    return 1
}

wait_for_port "${POSTGRES_HOST:-postgres}" "${POSTGRES_PORT:-5432}" "PostgreSQL"
wait_for_port "${MONGO_HOST:-mongo}" "${MONGO_PORT:-27017}" "MongoDB"
wait_for_port "minio" "9000" "MinIO"
wait_for_port "nessie" "19120" "Nessie"

echo "All services are ready."
