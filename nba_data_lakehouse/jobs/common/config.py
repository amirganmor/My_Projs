"""
Centralised configuration loaded from environment variables and configs/settings.yaml.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class PostgresConfig:
    host: str = field(default_factory=lambda: _env("POSTGRES_HOST", "postgres"))
    port: int = field(default_factory=lambda: int(_env("POSTGRES_PORT", "5432")))
    user: str = field(default_factory=lambda: _env("POSTGRES_USER", "lakehouse"))
    password: str = field(default_factory=lambda: _env("POSTGRES_PASSWORD", "lakehouse123"))
    database: str = field(default_factory=lambda: _env("POSTGRES_DB", "nba_sources"))

    @property
    def jdbc_url(self) -> str:
        return f"jdbc:postgresql://{self.host}:{self.port}/{self.database}"

    @property
    def sqlalchemy_url(self) -> str:
        return f"postgresql+psycopg2://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass(frozen=True)
class MongoConfig:
    host: str = field(default_factory=lambda: _env("MONGO_HOST", "mongo"))
    port: int = field(default_factory=lambda: int(_env("MONGO_PORT", "27017")))
    username: str = field(default_factory=lambda: _env("MONGO_INITDB_ROOT_USERNAME", "mongo"))
    password: str = field(default_factory=lambda: _env("MONGO_INITDB_ROOT_PASSWORD", "mongo123"))
    database: str = field(default_factory=lambda: _env("MONGO_DB", "nba_scouting"))

    @property
    def uri(self) -> str:
        return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}"


@dataclass(frozen=True)
class MinioConfig:
    endpoint: str = field(default_factory=lambda: _env("MINIO_ENDPOINT", "http://minio:9000"))
    access_key: str = field(default_factory=lambda: _env("AWS_ACCESS_KEY_ID", "minioadmin"))
    secret_key: str = field(default_factory=lambda: _env("AWS_SECRET_ACCESS_KEY", "minioadmin123"))
    bucket: str = field(default_factory=lambda: _env("MINIO_BUCKET", "nba-lakehouse"))
    region: str = field(default_factory=lambda: _env("AWS_REGION", "us-east-1"))


@dataclass(frozen=True)
class NessieConfig:
    uri: str = field(default_factory=lambda: _env("NESSIE_URI", "http://nessie:19120/api/v1"))


@dataclass(frozen=True)
class IcebergConfig:
    warehouse: str = field(default_factory=lambda: _env("ICEBERG_WAREHOUSE", "s3://nba-lakehouse/iceberg-warehouse"))


@dataclass(frozen=True)
class MLflowConfig:
    tracking_uri: str = field(default_factory=lambda: _env("MLFLOW_TRACKING_URI", "http://mlflow:5001"))
    s3_endpoint: str = field(default_factory=lambda: _env("MLFLOW_S3_ENDPOINT_URL", "http://minio:9000"))


@dataclass(frozen=True)
class AppConfig:
    postgres: PostgresConfig = field(default_factory=PostgresConfig)
    mongo: MongoConfig = field(default_factory=MongoConfig)
    minio: MinioConfig = field(default_factory=MinioConfig)
    nessie: NessieConfig = field(default_factory=NessieConfig)
    iceberg: IcebergConfig = field(default_factory=IcebergConfig)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)

    # Paths inside Airflow container
    data_dir: str = field(default_factory=lambda: _env("DATA_DIR", "/opt/airflow/data"))
    seed_dir: str = field(default_factory=lambda: _env("SEED_DIR", "/opt/airflow/data/seed"))
    configs_dir: str = field(default_factory=lambda: _env("CONFIGS_DIR", "/opt/airflow/configs"))

    @property
    def seed_path(self) -> Path:
        return Path(self.seed_dir)

    @property
    def api_mock_path(self) -> Path:
        return self.seed_path / "api_mock"

    @property
    def files_path(self) -> Path:
        return self.seed_path / "files"

    @property
    def postgres_seed_path(self) -> Path:
        return self.seed_path / "postgres"

    @property
    def mongo_seed_path(self) -> Path:
        return self.seed_path / "mongo"


def get_config() -> AppConfig:
    return AppConfig()


def load_yaml_config(name: str) -> dict:
    """Load a YAML config file from the configs directory."""
    cfg = get_config()
    path = Path(cfg.configs_dir) / name
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}
