"""
Score players to find underrated/undervalued ones.

Uses predicted salary (from value model) vs actual salary, with filters
to exclude established stars and focus on genuine hidden gems.

Key methodology:
- Ratio-based ranking (predicted / actual) not raw dollar gap
- Salary cap: exclude players above 75th percentile salary
- Min games (>= 40) and min minutes (>= 15) filters
- Only players where predicted > actual (truly undervalued)

Writes gold.scores_underrated_players.
"""
from __future__ import annotations

import os

import mlflow
import numpy as np
import pandas as pd
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import NullType, StringType

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.schemas import GOLD_TABLES
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("scoring.underrated")

FEATURE_COLS = [
    "AGE", "GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV",
    "FG_PCT", "FG3_PCT", "FT_PCT", "TS_PCT", "USG_PCT",
    "OFF_RATING", "DEF_RATING", "NET_RATING", "PIE",
    "total_games_missed", "injury_count",
    "prev_PTS", "prev_REB", "prev_AST", "prev_MIN",
]

MIN_GP = 40
MIN_MINUTES = 15.0
SALARY_PERCENTILE_CAP = 0.75
ALL_STAR_PTS_THRESHOLD = 22.0


def _cast_null_columns(df: DataFrame) -> DataFrame:
    for field in df.schema.fields:
        if isinstance(field.dataType, NullType):
            df = df.withColumn(field.name, F.col(field.name).cast(StringType()))
    return df


def score() -> int:
    cfg = get_config()
    os.environ["MLFLOW_TRACKING_URI"] = cfg.mlflow.tracking_uri
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = cfg.mlflow.s3_endpoint
    os.environ["AWS_ACCESS_KEY_ID"] = cfg.minio.access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = cfg.minio.secret_key

    spark = get_spark("score_underrated")
    try:
        df = spark.table(GOLD_TABLES["features_value_model"])
        pdf = df.toPandas()
    finally:
        stop_spark(spark)

    if pdf.empty:
        log.warning("No feature data available for scoring")
        return 0

    latest_season = pdf["SEASON"].max()
    log.info(f"Latest season in features: {latest_season}")

    scoring_df = pdf[pdf["SEASON"] == latest_season].copy()
    log.info(f"Players in latest season before filters: {len(scoring_df)}")

    # --- Filters ---
    if "GP" in scoring_df.columns:
        scoring_df = scoring_df[scoring_df["GP"] >= MIN_GP]
    if "MIN" in scoring_df.columns:
        scoring_df = scoring_df[scoring_df["MIN"] >= MIN_MINUTES]

    scoring_df = scoring_df[scoring_df["salary"].notna() & (scoring_df["salary"] > 0)]

    salary_cap = scoring_df["salary"].quantile(SALARY_PERCENTILE_CAP)
    log.info(f"Salary 75th percentile cap: ${salary_cap:,.0f}")
    scoring_df = scoring_df[scoring_df["salary"] <= salary_cap]

    log.info(f"Players after filters: {len(scoring_df)}")
    if len(scoring_df) < 10:
        log.warning("Too few players after filters")
        return 0

    available = [c for c in FEATURE_COLS if c in scoring_df.columns]
    scoring_df[available] = scoring_df[available].fillna(0)

    # --- Model ---
    try:
        mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
        experiment = mlflow.get_experiment_by_name("nba_player_value_model")
        if experiment:
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["metrics.mae ASC"],
            )
            if not runs.empty:
                best_run_id = runs.iloc[0]["run_id"]
                model = mlflow.sklearn.load_model(f"runs:/{best_run_id}/model")
                log.info(f"Loaded model from MLflow run {best_run_id}")
            else:
                raise ValueError("No runs found")
        else:
            raise ValueError("Experiment not found")
    except Exception as e:
        log.warning(f"Could not load MLflow model: {e}. Training inline...")
        from sklearn.ensemble import RandomForestRegressor

        train_df = pdf[pdf["SEASON"] < latest_season].copy()
        train_df[available] = train_df[available].fillna(0)
        train_df = train_df.dropna(subset=["salary"])
        train_df = train_df[train_df["salary"] > 0]
        if len(train_df) < 30:
            log.warning("Not enough training data")
            return 0
        model = RandomForestRegressor(
            n_estimators=200, max_depth=12, random_state=42, n_jobs=-1,
        )
        model.fit(train_df[available].values, train_df["salary"].values)

    X = scoring_df[available].values
    predicted_salary = model.predict(X)
    scoring_df["predicted_salary"] = predicted_salary
    scoring_df["undervaluation_gap"] = scoring_df["predicted_salary"] - scoring_df["salary"]

    # Only keep genuinely undervalued players (predicted > actual)
    scoring_df = scoring_df[scoring_df["undervaluation_gap"] > 0]

    # Ratio-based score: how many multiples of their salary are they worth?
    scoring_df["undervaluation_ratio"] = (
        scoring_df["predicted_salary"] / scoring_df["salary"]
    ).round(2)

    scoring_df["undervaluation_pct"] = (
        (scoring_df["undervaluation_gap"] / scoring_df["salary"]) * 100
    ).round(1)

    # Rank by ratio (highest ratio = most underrated)
    scoring_df = scoring_df.sort_values("undervaluation_ratio", ascending=False)
    scoring_df["rank"] = range(1, len(scoring_df) + 1)

    spark = get_spark("write_underrated_scores")
    try:
        spark.sql("CREATE NAMESPACE IF NOT EXISTS nessie.gold")
        sdf = spark.createDataFrame(scoring_df)
        sdf = _cast_null_columns(sdf)
        sdf.writeTo(GOLD_TABLES["scores_underrated_players"]).using("iceberg").createOrReplace()
        count = sdf.count()
    finally:
        stop_spark(spark)

    log.info(f"  gold.scores_underrated_players: {count:,} rows")
    return count


if __name__ == "__main__":
    score()
