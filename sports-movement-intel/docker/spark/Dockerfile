# Spark 4.1.3 / Scala 2.13 / Java 17 / Python 3.10 (Ubuntu 22.04) - verified tag on Docker Hub.
FROM apache/spark:4.1.3-scala2.13-java17-python3-ubuntu

USER root
COPY docker/spark/jars.lock docker/spark/fetch_jars.sh /tmp/
RUN bash /tmp/fetch_jars.sh /tmp/jars.lock /opt/spark/jars/ && rm /tmp/fetch_jars.sh

# Python deps for pandas UDF / applyInPandasWithState and sinks (pinned for Python 3.10).
COPY docker/spark/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /opt/smip
COPY pyproject.toml README.md /opt/smip/
COPY smip /opt/smip/smip
COPY config /opt/smip/config
RUN pip3 install --no-cache-dir --no-deps -e /opt/smip

ENV SMIP_CONFIG_DIR=/opt/smip/config \
    PYSPARK_PYTHON=python3 \
    PYTHONUNBUFFERED=1
USER spark
