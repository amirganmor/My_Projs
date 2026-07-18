FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "mlflow>=2.11.0,<2.15.0" \
    psycopg2-binary>=2.9.9 \
    boto3>=1.34.0

EXPOSE 5001

CMD mlflow server \
    --host 0.0.0.0 \
    --port 5001 \
    --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
    --default-artifact-root "${MLFLOW_ARTIFACT_ROOT}"
