# App image: API (+ built frontend), replay service, inference/analyst workers, MLflow server.
FROM node:22.23.3-alpine3.24 AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 MLFLOW_DISABLE_AGENT_HINT=1
WORKDIR /opt/smip
COPY pyproject.toml README.md ./
COPY smip ./smip
RUN pip install -e ".[app,ml,ai]" && pip install mlflow==3.16.1
COPY config ./config
COPY --from=ui /ui/dist ./frontend/dist
ENV SMIP_CONFIG_DIR=/opt/smip/config
RUN useradd -u 10001 -m smip
USER smip
