FROM apache/airflow:2.10.4-python3.11

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        build-essential \
        curl && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /hf-cache && chown -R airflow:0 /hf-cache

USER airflow

ENV HF_HOME=/hf-cache

RUN pip install --no-cache-dir \
      torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements/airflow.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY src /opt/airflow/src
