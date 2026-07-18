"""
Build trade target rankings using composite scoring.

Key methodology changes from original:
- Contract efficiency is the PRIMARY driver (weight 0.35)
- Exclude players above 85th percentile salary (supermax untradeable)
- Exclude players with no salary data (can't evaluate trade value)
- Below-median salary bonus rewards affordable contributors
- Raw performance weight reduced to 0.15 (trade value != best player)
- Age/upside weight increased to 0.20

Writes gold.scores_trade_targets.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import NullType, StringType

from jobs.common.logging_utils import get_logger
from jobs.common.schemas import GOLD_TABLES
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("scoring.trade_targets")

WEIGHTS = {
    "performance_score": 0.15,
    "contract_efficiency": 0.35,
    "age_upside_score": 0.20,
    "durability_score": 0.10,
    "efficiency_score": 0.10,
    "salary_bonus": 0.10,
}

MIN_GP = 30
MIN_MINUTES = 15.0
SALARY_PERCENTILE_CAP = 0.85


def _min_max_scale(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.5, index=series.index)
    return (series - mn) / (mx - mn)


def _cast_null_columns(df: DataFrame) -> DataFrame:
    for field in df.schema.fields:
        if isinstance(field.dataType, NullType):
            df = df.withColumn(field.name, F.col(field.name).cast(StringType()))
    return df


def score() -> int:
    spark = get_spark("build_trade_targets")
    try:
        df = spark.table(GOLD_TABLES["features_trade_target_model"])
        pdf = df.toPandas()
    finally:
        stop_spark(spark)

    if pdf.empty:
        log.warning("No trade target features available")
        return 0

    latest_season = pdf["SEASON"].max()
    scoring = pdf[pdf["SEASON"] == latest_season].copy()
    log.info(f"Building trade targets for {len(scoring)} players from {latest_season}")

    # --- Filters ---
    scoring = scoring[scoring["salary"].notna() & (scoring["salary"] > 0)]
    log.info(f"After removing no-salary: {len(scoring)}")

    if "GP" in scoring.columns:
        scoring = scoring[scoring["GP"] >= MIN_GP]
    if "MIN" in scoring.columns:
        scoring = scoring[scoring["MIN"] >= MIN_MINUTES]
    log.info(f"After GP/MIN filter: {len(scoring)}")

    salary_cap = scoring["salary"].quantile(SALARY_PERCENTILE_CAP)
    log.info(f"Salary 85th percentile cap: ${salary_cap:,.0f}")
    scoring = scoring[scoring["salary"] <= salary_cap]
    log.info(f"After salary cap filter: {len(scoring)}")

    if len(scoring) < 10:
        log.warning("Too few players after filters")
        return 0

    # --- Normalize components to 0-1 ---
    for col in ["performance_score", "contract_efficiency", "age_upside_score", "durability_score"]:
        if col in scoring.columns:
            scoring[f"{col}_norm"] = _min_max_scale(scoring[col].fillna(0))
        else:
            scoring[f"{col}_norm"] = 0.5

    if "TS_PCT" in scoring.columns:
        scoring["efficiency_score_norm"] = _min_max_scale(scoring["TS_PCT"].fillna(0.5))
    else:
        scoring["efficiency_score_norm"] = 0.5

    # Below-median salary bonus: affordable players get extra trade appeal
    median_salary = scoring["salary"].median()
    scoring["salary_bonus_norm"] = np.where(
        scoring["salary"] <= median_salary,
        _min_max_scale((median_salary - scoring["salary"]).clip(lower=0)),
        0.0,
    )

    # --- Composite score ---
    scoring["trade_target_score"] = (
        WEIGHTS["performance_score"] * scoring["performance_score_norm"] +
        WEIGHTS["contract_efficiency"] * scoring["contract_efficiency_norm"] +
        WEIGHTS["age_upside_score"] * scoring["age_upside_score_norm"] +
        WEIGHTS["durability_score"] * scoring["durability_score_norm"] +
        WEIGHTS["efficiency_score"] * scoring["efficiency_score_norm"] +
        WEIGHTS["salary_bonus"] * scoring["salary_bonus_norm"]
    ).round(4)

    scoring = scoring.sort_values("trade_target_score", ascending=False)
    scoring["rank"] = range(1, len(scoring) + 1)

    scoring["tier"] = pd.cut(
        scoring["trade_target_score"],
        bins=[0, 0.3, 0.5, 0.7, 1.01],
        labels=["Low Value", "Moderate", "Strong Target", "Elite Target"],
    )

    spark = get_spark("write_trade_targets")
    try:
        spark.sql("CREATE NAMESPACE IF NOT EXISTS nessie.gold")
        sdf = spark.createDataFrame(scoring)
        sdf = _cast_null_columns(sdf)
        sdf.writeTo(GOLD_TABLES["scores_trade_targets"]).using("iceberg").createOrReplace()
        count = sdf.count()
    finally:
        stop_spark(spark)

    log.info(f"  gold.scores_trade_targets: {count:,} rows")
    return count


if __name__ == "__main__":
    score()
