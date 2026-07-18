FROM apache/airflow:2.8.1-python3.11

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        default-jdk \
        curl \
        procps && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/default-java
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# Iceberg / Nessie / S3 JARs for PySpark
ENV SPARK_JARS_DIR=/opt/spark-jars
RUN mkdir -p ${SPARK_JARS_DIR}

RUN curl -sL -o ${SPARK_JARS_DIR}/iceberg-spark-runtime.jar \
      https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.5.0/iceberg-spark-runtime-3.5_2.12-1.5.0.jar && \
    curl -sL -o ${SPARK_JARS_DIR}/iceberg-aws-bundle.jar \
      https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-aws-bundle/1.5.0/iceberg-aws-bundle-1.5.0.jar && \
    curl -sL -o ${SPARK_JARS_DIR}/nessie-spark-extensions.jar \
      https://repo1.maven.org/maven2/org/projectnessie/nessie-integrations/nessie-spark-extensions-3.5_2.12/0.76.0/nessie-spark-extensions-3.5_2.12-0.76.0.jar && \
    curl -sL -o ${SPARK_JARS_DIR}/hadoop-aws.jar \
      https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/3.3.4/hadoop-aws-3.3.4.jar && \
    curl -sL -o ${SPARK_JARS_DIR}/aws-java-sdk-bundle.jar \
      https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.12.262/aws-java-sdk-bundle-1.12.262.jar && \
    curl -sL -o ${SPARK_JARS_DIR}/postgresql-jdbc.jar \
      https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.1/postgresql-42.7.1.jar

USER airflow

COPY requirements/airflow.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY jobs /opt/airflow/jobs
COPY configs /opt/airflow/configs
COPY tests /opt/airflow/tests
