"""Runtime settings resolved from environment variables.

Defaults target the host (ports published by docker-compose on 127.0.0.1). Containers
override them through docker-compose environment blocks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("SMIP_DATA_DIR", str(REPO_ROOT / "data"))))
    config_dir: Path = field(default_factory=lambda: Path(_env("SMIP_CONFIG_DIR", str(REPO_ROOT / "config"))))
    kafka_bootstrap: str = field(default_factory=lambda: _env("SMIP_KAFKA_BOOTSTRAP", "127.0.0.1:19092"))
    clickhouse_host: str = field(default_factory=lambda: _env("SMIP_CLICKHOUSE_HOST", "127.0.0.1"))
    clickhouse_port: int = field(default_factory=lambda: int(_env("SMIP_CLICKHOUSE_PORT", "18123")))
    clickhouse_user: str = field(default_factory=lambda: _env("SMIP_CLICKHOUSE_USER", "smip"))
    clickhouse_password: str = field(default_factory=lambda: _env("SMIP_CLICKHOUSE_PASSWORD", "smip-local"))
    clickhouse_db: str = field(default_factory=lambda: _env("SMIP_CLICKHOUSE_DB", "smip"))
    iceberg_rest_uri: str = field(default_factory=lambda: _env("SMIP_ICEBERG_REST_URI", "http://127.0.0.1:18181"))
    s3_endpoint: str = field(default_factory=lambda: _env("SMIP_S3_ENDPOINT", "http://127.0.0.1:17070"))
    s3_access_key: str = field(default_factory=lambda: _env("SMIP_S3_ACCESS_KEY", "smip"))
    s3_secret_key: str = field(default_factory=lambda: _env("SMIP_S3_SECRET_KEY", "smip-local-secret"))
    s3_region: str = field(default_factory=lambda: _env("SMIP_S3_REGION", "us-east-1"))
    warehouse: str = field(default_factory=lambda: _env("SMIP_WAREHOUSE", "s3://warehouse/"))
    api_url: str = field(default_factory=lambda: _env("SMIP_API_URL", "http://127.0.0.1:18000"))
    ollama_url: str = field(default_factory=lambda: _env("SMIP_OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: _env("SMIP_OLLAMA_MODEL", "qwen2.5:7b-instruct"))
    mlflow_uri: str = field(default_factory=lambda: _env("SMIP_MLFLOW_URI", str(REPO_ROOT / "artifacts" / "mlruns")))
    qdrant_url: str = field(default_factory=lambda: _env("SMIP_QDRANT_URL", "http://127.0.0.1:16333"))
    # Public demo mode: only redistributable (MIT SkillCorner) data is listed or served.
    public_demo: bool = field(default_factory=lambda: _env("SMIP_PUBLIC_DEMO", "0") == "1")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def normalized_dir(self) -> Path:
        return self.data_dir / "normalized"

    @property
    def state_dir(self) -> Path:
        return self.data_dir / "state"


def get_settings() -> Settings:
    return Settings()
