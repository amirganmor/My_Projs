# Airflow 3.3.2 (official image, Python 3.12). DAG tasks call the `smip` CLI, which is installed in its
# own virtualenv so Airflow's pinned dependencies are never modified.
FROM apache/airflow:3.3.2-python3.12
USER root
RUN mkdir -p /opt/smip-venv && chown airflow: /opt/smip-venv
USER airflow
COPY --chown=airflow pyproject.toml README.md /opt/smip/
COPY --chown=airflow smip /opt/smip/smip
COPY --chown=airflow config /opt/smip/config
RUN python -m venv /opt/smip-venv \
    && /opt/smip-venv/bin/pip install --no-cache-dir -e "/opt/smip[app,ml]"
ENV SMIP_CONFIG_DIR=/opt/smip/config \
    SMIP_BIN=/opt/smip-venv/bin/smip
