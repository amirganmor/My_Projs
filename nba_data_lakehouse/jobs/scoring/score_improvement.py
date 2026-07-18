"""
Score players to identify breakout/improvement candidates for next season.

Key methodology:
- Age <= 27: breakout candidates are young, not established veterans
- Exclude proven stars: PTS >= 22 AND top-25% salary are already elite
- Min GP >= 30: enough sample for reliable signal
- Score the LATEST available season (predict who breaks out NEXT)
- Bonus for positive trajectory (PTS_delta > 0, TS_PCT_delta > 0)

Writes gold.scores_improvement_candidates.
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

log = get_logger("scoring.improvement")

FEATURE_COLS = [
    "AGE", "GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV",
    "FG_PCT", "FG3_PCT", "TS_PCT", "USG_PCT", "NET_RATING", "PIE",
    "prev_PTS", "prev_REB", "prev_AST", "prev_MIN",
    "PTS_delta", "REB_delta", "AST_delta", "MIN_delta",
    "TS_PCT_delta", "NET_RATING_delta",
    "total_games_missed", "injury_count",
]

MAX_AGE = 27
MIN_GP = 30
STAR_PTS_THRESHOLD = 22.0
STAR_SALARY_PERCENTILE = 0.75


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

    spark = get_spark("score_improvement")
    try:
        df = spark.table(GOLD_TABLES["features_improvement_model"])
        pdf = df.toPandas()
    finally:
        stop_spark(spark)

    if pdf.empty:
        log.warning("No feature data available")
        return 0

    latest_season = pdf["SEASON"].max()
    log.info(f"Latest season in features: {latest_season}")

    # The latest season rows have next_PTS=NULL (no future data yet).
    # Those are exactly the rows we want to SCORE (predict breakout next).
    scoring_df = pdf[pdf["SEASON"] == latest_season].copy()
    log.info(f"Players in latest season before filters: {len(scoring_df)}")

    # --- Filters: focus on young breakout candidates ---
    if "AGE" in scoring_df.columns:
        scoring_df = scoring_df[scoring_df["AGE"] <= MAX_AGE]
        log.info(f"After age <= {MAX_AGE}: {len(scoring_df)}")

    if "GP" in scoring_df.columns:
        scoring_df = scoring_df[scoring_df["GP"] >= MIN_GP]
        log.info(f"After GP >= {MIN_GP}: {len(scoring_df)}")

    # Exclude established stars using two complementary filters:
    # 1) High scoring + high salary → proven elite with big contract
    # 2) Very high scoring alone → obvious star even without salary data
    OBVIOUS_STAR_PTS = 25.0
    if "PTS" in scoring_df.columns:
        has_salary = scoring_df["salary"].notna() & (scoring_df["salary"] > 0)
        salary_valid = scoring_df[has_salary]
        if len(salary_valid) > 0:
            salary_75th = salary_valid["salary"].quantile(STAR_SALARY_PERCENTILE)
            is_star_with_contract = (
                (scoring_df["PTS"] >= STAR_PTS_THRESHOLD) & has_salary &
                (scoring_df["salary"] >= salary_75th)
            )
        else:
            is_star_with_contract = pd.Series(False, index=scoring_df.index)

        is_obvious_star = scoring_df["PTS"] >= OBVIOUS_STAR_PTS
        scoring_df = scoring_df[~(is_star_with_contract | is_obvious_star)]
        log.info(f"After excluding established stars: {len(scoring_df)}")

    if len(scoring_df) < 10:
        log.warning("Too few players after filters")
        return 0

    available = [c for c in FEATURE_COLS if c in scoring_df.columns]
    scoring_df[available] = scoring_df[available].fillna(0)

    # --- Model: train on historical seasons where we know the outcome ---
    train_df = pdf[pdf["next_PTS"].notna()].copy()
    train_df[available] = train_df[available].fillna(0)
    train_df = train_df.dropna(subset=["improved_flag"])

    try:
        mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
        experiment = mlflow.get_experiment_by_name("nba_player_improvement_model")
        if experiment:
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["metrics.f1_score DESC"],
            )
            if not runs.empty:
                best_run_id = runs.iloc[0]["run_id"]
                model = mlflow.sklearn.load_model(f"runs:/{best_run_id}/model")
                log.info(f"Loaded model from MLflow run {best_run_id}")
            else:
                raise ValueError("No runs")
        else:
            raise ValueError("No experiment")
    except Exception as e:
        log.warning(f"Could not load MLflow model: {e}. Training inline...")
        from sklearn.ensemble import GradientBoostingClassifier

        if len(train_df) < 30:
            log.warning("Not enough training data for inline model")
            return 0
        model = GradientBoostingClassifier(
            n_estimators=150, max_depth=5, learning_rate=0.1, random_state=42,
        )
        model.fit(
            train_df[available].values,
            train_df["improved_flag"].values.astype(int),
        )

    X = scoring_df[available].values
    raw_proba = (
        model.predict_proba(X)[:, 1]
        if hasattr(model, "predict_proba")
        else model.predict(X).astype(float)
    )
    scoring_df["improvement_probability"] = raw_proba

    # Trajectory bonus: reward players already on an upward arc
    trajectory_bonus = np.zeros(len(scoring_df))
    if "PTS_delta" in scoring_df.columns:
        pts_d = scoring_df["PTS_delta"].values
        trajectory_bonus += np.where(pts_d > 0, np.clip(pts_d / 5.0, 0, 0.15), 0)
    if "TS_PCT_delta" in scoring_df.columns:
        ts_d = scoring_df["TS_PCT_delta"].values
        trajectory_bonus += np.where(ts_d > 0, np.clip(ts_d * 2.0, 0, 0.10), 0)
    if "AST_delta" in scoring_df.columns:
        ast_d = scoring_df["AST_delta"].values
        trajectory_bonus += np.where(ast_d > 0, np.clip(ast_d / 3.0, 0, 0.05), 0)

    scoring_df["trajectory_bonus"] = trajectory_bonus.round(3)
    scoring_df["breakout_score"] = (
        scoring_df["improvement_probability"] + scoring_df["trajectory_bonus"]
    ).clip(0, 1).round(4)

    scoring_df["predicted_improved"] = (scoring_df["breakout_score"] >= 0.5).astype(int)

    scoring_df = scoring_df.sort_values("breakout_score", ascending=False)
    scoring_df["rank"] = range(1, len(scoring_df) + 1)

    spark = get_spark("write_improvement_scores")
    try:
        spark.sql("CREATE NAMESPACE IF NOT EXISTS nessie.gold")
        sdf = spark.createDataFrame(scoring_df)
        sdf = _cast_null_columns(sdf)
        sdf.writeTo(GOLD_TABLES["scores_improvement_candidates"]).using("iceberg").createOrReplace()
        count = sdf.count()
    finally:
        stop_spark(spark)

    log.info(f"  gold.scores_improvement_candidates: {count:,} rows")
    return count


if __name__ == "__main__":
    score()
