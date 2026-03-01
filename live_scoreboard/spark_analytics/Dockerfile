FROM apache/spark:3.5.0

USER root

RUN pip install pyspark==3.5.0

# Pre-download Kafka + PostgreSQL JARs and all transitive dependencies at build time
RUN mkdir -p /opt/spark/extra-jars && \
    cd /opt/spark/extra-jars && \
    curl -fSL -O https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.0/spark-sql-kafka-0-10_2.12-3.5.0.jar && \
    curl -fSL -O https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.4.1/kafka-clients-3.4.1.jar && \
    curl -fSL -O https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.0/spark-token-provider-kafka-0-10_2.12-3.5.0.jar && \
    curl -fSL -O https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar && \
    curl -fSL -O https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.1/postgresql-42.7.1.jar

COPY stream_to_postgres.py /opt/spark/work-dir/

USER spark

ENTRYPOINT ["/opt/spark/bin/spark-submit", \
    "--master", "spark://spark-master:7077", \
    "--jars", "/opt/spark/extra-jars/spark-sql-kafka-0-10_2.12-3.5.0.jar,/opt/spark/extra-jars/kafka-clients-3.4.1.jar,/opt/spark/extra-jars/spark-token-provider-kafka-0-10_2.12-3.5.0.jar,/opt/spark/extra-jars/commons-pool2-2.11.1.jar,/opt/spark/extra-jars/postgresql-42.7.1.jar", \
    "/opt/spark/work-dir/stream_to_postgres.py"]
