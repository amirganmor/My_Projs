"""Load CSV seed files into PostgreSQL source tables."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import text, inspect

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.postgres_utils import get_engine, get_row_count

log = get_logger("seed.postgres")


def _get_table_columns(engine, table: str) -> set[str]:
    """Return the set of column names for a PostgreSQL table."""
    insp = inspect(engine)
    return {col["name"] for col in insp.get_columns(table)}


def seed_postgres() -> dict[str, int]:
    """Load contracts, injuries, and rosters CSVs into Postgres. Returns row counts."""
    cfg = get_config()
    seed_path = cfg.postgres_seed_path
    engine = get_engine()
    counts: dict[str, int] = {}

    for table, filename in [
        ("contracts", "contracts.csv"),
        ("injuries", "injuries.csv"),
        ("rosters", "rosters.csv"),
    ]:
        csv_path = seed_path / filename
        if not csv_path.exists():
            log.warning(f"  Seed file not found: {csv_path}")
            counts[table] = 0
            continue

        df = pd.read_csv(csv_path)
        log.info(f"  Loading {filename} → {table} ({len(df):,} rows)")

        # Keep only columns that exist in the target table (auto-generated
        # columns like SERIAL PKs and DEFAULT cols are handled by Postgres).
        db_cols = _get_table_columns(engine, table)
        extra = set(df.columns) - db_cols
        if extra:
            log.info(f"  Dropping CSV columns not in {table} schema: {sorted(extra)}")
            df = df.drop(columns=list(extra))

        with engine.begin() as conn:
            conn.execute(text(f"TRUNCATE TABLE {table}"))

        df.to_sql(table, engine, if_exists="append", index=False, method="multi")
        counts[table] = get_row_count(table)
        log.info(f"  {table}: {counts[table]:,} rows loaded")

    return counts


if __name__ == "__main__":
    seed_postgres()
