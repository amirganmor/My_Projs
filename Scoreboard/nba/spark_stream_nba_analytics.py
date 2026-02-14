from pyspark.sql import SparkSession
from pyspark.sql.functions import from_json, col, explode, current_timestamp
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, ArrayType

# 1. Performance-Tuned Spark Session (Local Mode)
spark = (
    SparkSession.builder
    .appName("NBA_Kafka_Console_Stream")
    # Only include the essential Kafka JAR
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0")
    # Performance & Memory Tweaks for your Mac
    .config("spark.driver.memory", "8g")
    .config("spark.executor.memory", "8g")
    .config("spark.sql.shuffle.partitions", "4")  # Reduced for local development
    .config("spark.python.worker.reuse", "true")
    .getOrCreate()
)

# 2. Schema definition (Matches the nested JSON from your producer)
schema = StructType([
    StructField("games", ArrayType(
        StructType([
            StructField("gameId", StringType()),
            StructField("gameStatusText", StringType()),
            StructField("homeTeam", StructType([
                StructField("teamName", StringType()),
                StructField("score", IntegerType())
            ])),
            StructField("awayTeam", StructType([
                StructField("teamName", StringType()),
                StructField("score", IntegerType())
            ]))
        ])
    ))
])

# 3. Read from Kafka (Starting from earliest to see existing data)
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "nba_scoreboard") \
    .option("startingOffsets", "earliest") \
    .load()

# 4. Transform: JSON String -> Structured Columns -> Exploded Rows
clean_df = df.selectExpr("CAST(value AS STRING)") \
    .select(from_json(col("value"), schema).alias("data")) \
    .select(explode(col("data.games")).alias("game")) \
    .select(
        col("game.gameId"),
        col("game.homeTeam.teamName").alias("home_team"),
        col("game.homeTeam.score").alias("home_score"),
        col("game.awayTeam.teamName").alias("away_team"),
        col("game.awayTeam.score").alias("away_score"),
        current_timestamp().alias("processed_at")
    )

# 5. Output: Print to Console
query = clean_df.writeStream \
    .outputMode("append") \
    .format("console") \
    .option("truncate", "false") \
    .start()

query.awaitTermination()
