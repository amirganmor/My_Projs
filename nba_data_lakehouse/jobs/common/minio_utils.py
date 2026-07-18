"""MinIO / S3 helpers using boto3."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import boto3
import pandas as pd

from jobs.common.config import get_config


def get_s3_client():
    cfg = get_config().minio
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        region_name=cfg.region,
    )


def upload_file(local_path: str | Path, s3_key: str, bucket: str | None = None) -> None:
    cfg = get_config().minio
    client = get_s3_client()
    client.upload_file(str(local_path), bucket or cfg.bucket, s3_key)


def download_json(s3_key: str, bucket: str | None = None) -> Any:
    cfg = get_config().minio
    client = get_s3_client()
    resp = client.get_object(Bucket=bucket or cfg.bucket, Key=s3_key)
    return json.loads(resp["Body"].read())


def upload_json(data: Any, s3_key: str, bucket: str | None = None) -> None:
    cfg = get_config().minio
    client = get_s3_client()
    body = json.dumps(data, default=str).encode()
    client.put_object(Bucket=bucket or cfg.bucket, Key=s3_key, Body=body)


def upload_dataframe_parquet(df: pd.DataFrame, s3_key: str, bucket: str | None = None) -> None:
    cfg = get_config().minio
    client = get_s3_client()
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    client.put_object(Bucket=bucket or cfg.bucket, Key=s3_key, Body=buf.getvalue())


def download_dataframe_parquet(s3_key: str, bucket: str | None = None) -> pd.DataFrame:
    cfg = get_config().minio
    client = get_s3_client()
    resp = client.get_object(Bucket=bucket or cfg.bucket, Key=s3_key)
    buf = io.BytesIO(resp["Body"].read())
    return pd.read_parquet(buf)


def list_objects(prefix: str, bucket: str | None = None) -> list[str]:
    cfg = get_config().minio
    client = get_s3_client()
    resp = client.list_objects_v2(Bucket=bucket or cfg.bucket, Prefix=prefix)
    return [obj["Key"] for obj in resp.get("Contents", [])]
