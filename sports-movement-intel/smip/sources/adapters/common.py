"""Shared helpers for adapters: namespacing, direction handling and output writing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from smip.contracts.tables import EVENTS_SCHEMA, FRAMES_SCHEMA, TRACKING_SCHEMA, cast_to, validate_match_meta
from smip.sources.fetch import file_digest

ADAPTER_VERSION = "1.0.0"


def ns_match(source: str, mid) -> str:
    return f"{source}:{mid}"


def ns_team(source: str, tid) -> str | None:
    return None if tid is None else f"{source}:team:{tid}"


def ns_player(source: str, pid) -> str | None:
    return None if pid is None else f"{source}:player:{pid}"


def apply_attack_direction(x: np.ndarray, y: np.ndarray, sign: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rotate 180 degrees where sign == -1 so the team attacks toward +x. NaN sign -> NaN output."""
    return x * sign, y * sign


@dataclass
class NormalizedMatch:
    meta: dict
    frames: dict[str, list]
    tracking: dict[str, list | np.ndarray]
    events: dict[str, list] | None = None
    extra_tables: dict[str, pa.Table] = field(default_factory=dict)
    quality: dict = field(default_factory=dict)
    raw_assets: list[Path] = field(default_factory=list)


def write_normalized(nm: NormalizedMatch, out_root: Path, raw_root: Path) -> Path:
    validate_match_meta(nm.meta)
    out = out_root / nm.meta["source"] / str(nm.meta["source_match_id"])
    out.mkdir(parents=True, exist_ok=True)
    frames = cast_to(pa.table(nm.frames), FRAMES_SCHEMA)
    tracking = cast_to(pa.table(nm.tracking), TRACKING_SCHEMA)
    pq.write_table(frames, out / "frames.parquet", compression="zstd")
    pq.write_table(tracking, out / "tracking.parquet", compression="zstd", row_group_size=250_000)
    if nm.events is not None:
        pq.write_table(cast_to(pa.table(nm.events), EVENTS_SCHEMA), out / "events.parquet", compression="zstd")
    for name, tbl in nm.extra_tables.items():
        pq.write_table(tbl, out / f"{name}.parquet", compression="zstd")
    nm.meta["provenance"] = {
        "adapter_version": ADAPTER_VERSION,
        "normalized_at": datetime.now(timezone.utc).isoformat(),
        "raw_assets": [{"path": str(p.relative_to(raw_root)), "sha256": file_digest(p)} for p in nm.raw_assets],
    }
    nm.meta["counts"] = {
        "frames": frames.num_rows,
        "position_rows": tracking.num_rows,
        "events": 0 if nm.events is None else len(next(iter(nm.events.values()), [])),
        "players": len(nm.meta["players"]),
    }
    (out / "match.json").write_text(json.dumps(nm.meta, indent=1, default=str))
    (out / "quality.json").write_text(json.dumps(nm.quality, indent=1, default=str))
    return out


def gap_segments(times_ms: np.ndarray, has_data: np.ndarray, expected_dt_ms: float, min_gap_ms: float) -> list[dict]:
    """Contiguous runs where has_data is False (or time jumps) longer than min_gap_ms."""
    segs = []
    start = None
    for i, ok in enumerate(has_data):
        if not ok and start is None:
            start = i
        elif ok and start is not None:
            dur = times_ms[i] - times_ms[start]
            if dur >= min_gap_ms:
                segs.append({"start_ms": int(times_ms[start]), "end_ms": int(times_ms[i]), "duration_ms": int(dur)})
            start = None
    if start is not None:
        dur = times_ms[-1] - times_ms[start] + expected_dt_ms
        if dur >= min_gap_ms:
            segs.append({"start_ms": int(times_ms[start]), "end_ms": int(times_ms[-1]), "duration_ms": int(dur)})
    return segs
