"""Tests for configuration module."""
import os
import pytest


def test_config_defaults():
    from jobs.common.config import AppConfig
    cfg = AppConfig()
    assert cfg.postgres.host in ("postgres", "localhost", os.environ.get("POSTGRES_HOST", "postgres"))
    assert cfg.mongo.database == os.environ.get("MONGO_DB", "nba_scouting")
    assert cfg.minio.bucket == os.environ.get("MINIO_BUCKET", "nba-lakehouse")


def test_postgres_urls():
    from jobs.common.config import PostgresConfig
    pg = PostgresConfig()
    assert "postgresql" in pg.sqlalchemy_url
    assert "jdbc:postgresql" in pg.jdbc_url


def test_seed_paths():
    from jobs.common.config import AppConfig
    cfg = AppConfig()
    assert "seed" in str(cfg.seed_path)
    assert "api_mock" in str(cfg.api_mock_path)
