FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl \
        build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
      torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements/api.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY src /app/src
COPY api /app/api

ENV HF_HOME=/hf-cache

EXPOSE 8000

HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1

ENTRYPOINT ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
