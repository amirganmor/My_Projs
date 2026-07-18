"""
Train a model to predict player market value (salary) from performance features.

Uses gold.features_value_model as input.
Logs experiments to MLflow. Saves artifacts to MinIO.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.schemas import GOLD_TABLES
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("train.value_model")

FEATURE_COLS = [
    "AGE", "GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV",
    "FG_PCT", "FG3_PCT", "FT_PCT", "TS_PCT", "USG_PCT",
    "OFF_RATING", "DEF_RATING", "NET_RATING", "PIE",
    "total_games_missed", "injury_count",
    "prev_PTS", "prev_REB", "prev_AST", "prev_MIN",
]

TARGET = "salary"
TRAIN_CUTOFF = "2022-23"
VAL_SEASON = "2023-24"


def load_features() -> pd.DataFrame:
    spark = get_spark("load_value_features")
    try:
        df = spark.table(GOLD_TABLES["features_value_model"])
        pdf = df.toPandas()
    finally:
        stop_spark(spark)
    return pdf


def prepare_data(pdf: pd.DataFrame) -> tuple:
    """Time-based split: train ≤ cutoff, validation = val season, test = latest."""
    available_features = [c for c in FEATURE_COLS if c in pdf.columns]
    log.info(f"  Available features: {len(available_features)}/{len(FEATURE_COLS)}")

    pdf = pdf.dropna(subset=[TARGET])
    pdf[available_features] = pdf[available_features].fillna(0)

    train = pdf[pdf["SEASON"] <= TRAIN_CUTOFF]
    val = pdf[pdf["SEASON"] == VAL_SEASON]
    test = pdf[pdf["SEASON"] > VAL_SEASON]

    log.info(f"  Train: {len(train):,}  Val: {len(val):,}  Test: {len(test):,}")

    X_train = train[available_features].values
    y_train = train[TARGET].values
    X_val = val[available_features].values if len(val) > 0 else None
    y_val = val[TARGET].values if len(val) > 0 else None
    X_test = test[available_features].values if len(test) > 0 else None
    y_test = test[TARGET].values if len(test) > 0 else None

    return X_train, y_train, X_val, y_val, X_test, y_test, available_features, test


def train() -> dict:
    cfg = get_config()

    # MLflow setup
    os.environ["MLFLOW_TRACKING_URI"] = cfg.mlflow.tracking_uri
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = cfg.mlflow.s3_endpoint
    os.environ["AWS_ACCESS_KEY_ID"] = cfg.minio.access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = cfg.minio.secret_key

    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    experiment_name = "nba_player_value_model"
    mlflow.set_experiment(experiment_name)

    log.info("Loading features for value model...")
    pdf = load_features()
    if pdf.empty:
        log.warning("No features available — skipping training")
        return {}

    X_train, y_train, X_val, y_val, X_test, y_test, features, test_df = prepare_data(pdf)
    if len(X_train) < 50:
        log.warning(f"Insufficient training data ({len(X_train)} rows)")
        return {}

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val) if X_val is not None else None

    models = {
        "linear_regression": LinearRegression(),
        "random_forest": RandomForestRegressor(n_estimators=200, max_depth=15, random_state=42, n_jobs=-1),
        "gradient_boosting": GradientBoostingRegressor(n_estimators=200, max_depth=6, random_state=42),
    }

    best_model = None
    best_score = float("inf")
    best_name = ""
    all_results = {}

    for name, model in models.items():
        log.info(f"  Training {name}...")
        with mlflow.start_run(run_name=f"value_{name}_{datetime.utcnow().strftime('%Y%m%d')}"):
            model.fit(X_train_scaled, y_train)

            # Validation metrics
            if X_val_scaled is not None and len(X_val_scaled) > 0:
                y_pred = model.predict(X_val_scaled)
                mae = mean_absolute_error(y_val, y_pred)
                rmse = np.sqrt(mean_squared_error(y_val, y_pred))
                r2 = r2_score(y_val, y_pred)
            else:
                # Use cross-validation on training data
                cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5, scoring="neg_mean_absolute_error")
                mae = -cv_scores.mean()
                rmse = 0.0
                r2 = 0.0

            mlflow.log_param("model_type", name)
            mlflow.log_param("n_features", len(features))
            mlflow.log_param("n_train_rows", len(X_train))
            mlflow.log_param("train_cutoff", TRAIN_CUTOFF)
            mlflow.log_metric("mae", mae)
            mlflow.log_metric("rmse", rmse)
            mlflow.log_metric("r2", r2)

            # Feature importance
            if hasattr(model, "feature_importances_"):
                importance = dict(zip(features, model.feature_importances_.tolist()))
                mlflow.log_dict(importance, "feature_importance.json")

            mlflow.sklearn.log_model(model, artifact_path="model")
            log.info(f"    {name}: MAE={mae:,.0f}  RMSE={rmse:,.0f}  R²={r2:.3f}")

            all_results[name] = {"mae": mae, "rmse": rmse, "r2": r2}
            if mae < best_score:
                best_score = mae
                best_model = model
                best_name = name

    log.info(f"  Best model: {best_name} (MAE={best_score:,.0f})")
    return {"best_model": best_name, "results": all_results, "features": features}


if __name__ == "__main__":
    train()
