"""
Train a model to predict which players will improve next season.

Uses gold.features_improvement_model as input.
Target: improved_flag (binary — PTS increase >= 2.0 with GP >= 20).
"""
from __future__ import annotations

import os
from datetime import datetime

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.schemas import GOLD_TABLES
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("train.improvement_model")

FEATURE_COLS = [
    "AGE", "GP", "MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV",
    "FG_PCT", "FG3_PCT", "TS_PCT", "USG_PCT", "NET_RATING", "PIE",
    "prev_PTS", "prev_REB", "prev_AST", "prev_MIN",
    "PTS_delta", "REB_delta", "AST_delta", "MIN_delta",
    "TS_PCT_delta", "NET_RATING_delta",
    "total_games_missed", "injury_count",
]

TARGET = "improved_flag"
TRAIN_CUTOFF = "2022-23"


def load_features() -> pd.DataFrame:
    spark = get_spark("load_improvement_features")
    try:
        df = spark.table(GOLD_TABLES["features_improvement_model"])
        pdf = df.toPandas()
    finally:
        stop_spark(spark)
    return pdf


def train() -> dict:
    cfg = get_config()

    os.environ["MLFLOW_TRACKING_URI"] = cfg.mlflow.tracking_uri
    os.environ["MLFLOW_S3_ENDPOINT_URL"] = cfg.mlflow.s3_endpoint
    os.environ["AWS_ACCESS_KEY_ID"] = cfg.minio.access_key
    os.environ["AWS_SECRET_ACCESS_KEY"] = cfg.minio.secret_key

    mlflow.set_tracking_uri(cfg.mlflow.tracking_uri)
    mlflow.set_experiment("nba_player_improvement_model")

    log.info("Loading features for improvement model...")
    pdf = load_features()
    if pdf.empty:
        log.warning("No features available")
        return {}

    available = [c for c in FEATURE_COLS if c in pdf.columns]
    log.info(f"  Available features: {len(available)}/{len(FEATURE_COLS)}")

    pdf = pdf.dropna(subset=[TARGET])
    pdf[available] = pdf[available].fillna(0)

    train_df = pdf[pdf["SEASON"] <= TRAIN_CUTOFF]
    test_df = pdf[pdf["SEASON"] > TRAIN_CUTOFF]

    if len(train_df) < 50:
        log.warning(f"Insufficient training data ({len(train_df)} rows)")
        return {}

    X_train = train_df[available].values
    y_train = train_df[TARGET].values.astype(int)
    X_test = test_df[available].values if len(test_df) > 0 else None
    y_test = test_df[TARGET].values.astype(int) if len(test_df) > 0 else None

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test) if X_test is not None else None

    models = {
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=200, max_depth=5, random_state=42),
    }

    best_name = ""
    best_f1 = 0.0
    all_results = {}

    for name, model in models.items():
        log.info(f"  Training {name}...")
        with mlflow.start_run(run_name=f"improvement_{name}_{datetime.utcnow().strftime('%Y%m%d')}"):
            model.fit(X_train_s, y_train)

            if X_test_s is not None and len(X_test_s) > 0:
                y_pred = model.predict(X_test_s)
                y_prob = model.predict_proba(X_test_s)[:, 1] if hasattr(model, "predict_proba") else y_pred

                acc = accuracy_score(y_test, y_pred)
                f1 = f1_score(y_test, y_pred, zero_division=0)
                prec = precision_score(y_test, y_pred, zero_division=0)
                rec = recall_score(y_test, y_pred, zero_division=0)
                try:
                    auc = roc_auc_score(y_test, y_prob)
                except ValueError:
                    auc = 0.0
            else:
                acc = f1 = prec = rec = auc = 0.0

            mlflow.log_param("model_type", name)
            mlflow.log_param("n_features", len(available))
            mlflow.log_param("n_train_rows", len(X_train))
            mlflow.log_metric("accuracy", acc)
            mlflow.log_metric("f1_score", f1)
            mlflow.log_metric("precision", prec)
            mlflow.log_metric("recall", rec)
            mlflow.log_metric("auc_roc", auc)

            if hasattr(model, "feature_importances_"):
                importance = dict(zip(available, model.feature_importances_.tolist()))
                mlflow.log_dict(importance, "feature_importance.json")

            mlflow.sklearn.log_model(model, artifact_path="model")
            log.info(f"    {name}: Acc={acc:.3f}  F1={f1:.3f}  AUC={auc:.3f}")

            all_results[name] = {"accuracy": acc, "f1": f1, "auc": auc}
            if f1 > best_f1:
                best_f1 = f1
                best_name = name

    log.info(f"  Best model: {best_name} (F1={best_f1:.3f})")
    return {"best_model": best_name, "results": all_results}


if __name__ == "__main__":
    train()
