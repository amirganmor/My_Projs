"""ClickHouse client helpers (shared by Spark driver sink, API, replay service and CLI)."""

from __future__ import annotations

import math
import threading

import clickhouse_connect
import pandas as pd

from smip.config import get_settings

_local = threading.local()


def client():
    c = getattr(_local, "client", None)
    if c is None:
        s = get_settings()
        c = clickhouse_connect.get_client(
            host=s.clickhouse_host, port=s.clickhouse_port, username=s.clickhouse_user,
            password=s.clickhouse_password, database=s.clickhouse_db,
            settings={"max_execution_time": 30},
        )
        _local.client = c
    return c


_types: dict[str, dict[str, str]] = {}


def _column_types(table: str) -> dict[str, str]:
    if table not in _types:
        res = client().query(f"DESCRIBE TABLE {table}")
        _types[table] = {r[0]: r[1] for r in res.result_rows}
    return _types[table]


def _coerce(v, ctype: str):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if v is pd.NaT or (hasattr(pd, "isna") and not isinstance(v, (list, dict, str)) and pd.isna(v)):
            return None
    except (TypeError, ValueError):
        pass
    base = ctype.replace("Nullable(", "").replace("LowCardinality(", "").rstrip(")")
    if base.startswith(("Int", "UInt")):
        return int(v)
    if base.startswith("Float"):
        return float(v)
    if base == "Bool":
        return bool(v)
    if base == "String":
        return str(v)
    if base.startswith("DateTime"):
        ts = pd.Timestamp(v)
        return (ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")).to_pydatetime()
    return v


def insert_df(table: str, df) -> int:
    """Insert a pandas DataFrame, coercing values to the table's declared column types."""
    if df is None or len(df) == 0:
        return 0
    types = _column_types(table)
    cols = [c for c in df.columns if c in types]
    data = [[_coerce(v, types[c]) for c, v in zip(cols, row)]
            for row in df[cols].itertuples(index=False, name=None)]
    client().insert(table, data, column_names=cols)
    return len(data)


def _arrow_type(ctype: str):
    import pyarrow as pa

    base = ctype.replace("Nullable(", "").replace("LowCardinality(", "").rstrip(")")
    if base.startswith("DateTime64"):
        return pa.timestamp("ms", tz="UTC")
    return {"Int64": pa.int64(), "Int32": pa.int32(), "Int16": pa.int16(), "UInt64": pa.uint64(),
            "Float64": pa.float64(), "Float32": pa.float32(), "Bool": pa.bool_(), "String": pa.string()}[base]


INSERT_CHUNK_ROWS = 50_000


def insert_arrow(table: str, tbl) -> int:
    """Insert a pyarrow Table in bounded chunks (keeps ClickHouse and driver memory flat)."""
    import pyarrow as pa
    import pyarrow.compute as pc

    if tbl is None or tbl.num_rows == 0:
        return 0
    types = _column_types(table)
    cols, arrays = [], []
    for name in tbl.column_names:
        if name not in types:
            continue
        col = tbl.column(name)
        target = _arrow_type(types[name])
        if pa.types.is_floating(col.type) and not pa.types.is_floating(target):
            col = pc.if_else(pc.is_nan(col), pa.scalar(None, col.type), col)
        cols.append(name)
        arrays.append(col.cast(target, safe=False))
    out = pa.table(arrays, names=cols)
    for off in range(0, out.num_rows, INSERT_CHUNK_ROWS):
        client().insert_arrow(table, out.slice(off, INSERT_CHUNK_ROWS))
    return out.num_rows


def query_df(sql: str, params: dict | None = None):
    return client().query_df(sql, parameters=params or {})


def query_rows(sql: str, params: dict | None = None, settings: dict | None = None) -> list[dict]:
    res = client().query(sql, parameters=params or {}, settings=settings)
    return [dict(zip(res.column_names, r)) for r in res.result_rows]
