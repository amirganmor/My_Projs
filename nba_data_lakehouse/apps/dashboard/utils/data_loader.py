"""Utility to load Parquet exports from MinIO for the dashboard."""
from __future__ import annotations

import io
import os
from functools import lru_cache

import boto3
import pandas as pd
import streamlit as st

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
SECRET_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin123")
BUCKET = os.environ.get("MINIO_BUCKET", "nba-lakehouse")


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        region_name="us-east-1",
    )


@st.cache_data(ttl=300)
def load_parquet(s3_key: str) -> pd.DataFrame:
    """Load a Parquet file from MinIO. Returns empty DataFrame on failure."""
    try:
        client = _get_client()
        resp = client.get_object(Bucket=BUCKET, Key=s3_key)
        buf = io.BytesIO(resp["Body"].read())
        return pd.read_parquet(buf)
    except Exception as e:
        st.warning(f"Could not load {s3_key}: {e}")
        return pd.DataFrame()


def load_underrated() -> pd.DataFrame:
    return load_parquet("exports/scores_underrated_players.parquet")


def load_improvement() -> pd.DataFrame:
    return load_parquet("exports/scores_improvement_candidates.parquet")


def load_trade_targets() -> pd.DataFrame:
    return load_parquet("exports/scores_trade_targets.parquet")


def load_player_summary() -> pd.DataFrame:
    return load_parquet("exports/player_season_summary.parquet")


def load_data_quality() -> pd.DataFrame:
    return load_parquet("exports/data_quality_summary.parquet")


def load_source_coverage() -> pd.DataFrame:
    return load_parquet("exports/source_coverage_summary.parquet")


def list_exports() -> list[str]:
    """List all exported files in MinIO."""
    try:
        client = _get_client()
        resp = client.list_objects_v2(Bucket=BUCKET, Prefix="exports/")
        return [obj["Key"] for obj in resp.get("Contents", [])]
    except Exception:
        return []
