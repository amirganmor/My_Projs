"""PostgreSQL helpers using SQLAlchemy."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from jobs.common.config import get_config


def get_engine() -> Engine:
    cfg = get_config().postgres
    return create_engine(cfg.sqlalchemy_url, pool_pre_ping=True)


@contextmanager
def get_connection() -> Generator:
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


def read_table(table_name: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql_table(table_name, engine)


def read_query(sql: str) -> pd.DataFrame:
    engine = get_engine()
    return pd.read_sql(sql, engine)


def execute(sql: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(sql))


def load_csv_to_table(csv_path: str, table_name: str, if_exists: str = "append") -> int:
    """Load a CSV file into a PostgreSQL table. Returns row count."""
    df = pd.read_csv(csv_path)
    engine = get_engine()
    df.to_sql(table_name, engine, if_exists=if_exists, index=False)
    return len(df)


def get_row_count(table_name: str) -> int:
    with get_connection() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        return result.scalar() or 0
