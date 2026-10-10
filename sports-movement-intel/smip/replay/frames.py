"""Build canonical whole-frame messages (players array + ball object) from normalized parquet."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from smip.config import get_settings
from smip.contracts.models import CONTRACT_VERSION

ENTITY_FIELDS = ("entity_type", "source_player_id", "canonical_player_id", "team_id", "jersey", "x_m", "y_m",
                 "z_m", "x_att", "y_att", "x_src", "y_src", "z_src", "is_detected", "is_extrapolated",
                 "position_source", "confidence")


def match_dir(match_id: str) -> Path:
    source, mid = match_id.split(":", 1)
    return get_settings().normalized_dir / source / mid


def load_meta(match_id: str) -> dict:
    return json.loads((match_dir(match_id) / "match.json").read_text())


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def iter_frames(match_id: str, start_seq: int = 0, end_seq: int | None = None) -> Iterator[dict]:
    """Yield frame dicts (without session/replay fields) in canonical sequence order."""
    d = match_dir(match_id)
    meta = load_meta(match_id)
    frames = pq.read_table(d / "frames.parquet").to_pandas()
    trk = pq.read_table(d / "tracking.parquet", columns=["sequence", *ENTITY_FIELDS]).to_pandas()
    trk = trk.sort_values("sequence", kind="stable")
    seqs = trk["sequence"].to_numpy()
    cols = {c: trk[c].to_numpy(dtype=object) for c in ENTITY_FIELDS}
    starts = np.searchsorted(seqs, frames["sequence"].to_numpy(), side="left")
    ends = np.searchsorted(seqs, frames["sequence"].to_numpy(), side="right")
    base = {"schema_version": CONTRACT_VERSION, "record_type": "tracking_frame", "source": meta["source"],
            "source_revision": meta["source_revision"], "sport": meta["sport"], "match_id": match_id}
    for i, fr in enumerate(frames.itertuples(index=False)):
        seq = int(fr.sequence)
        if seq < start_seq or (end_seq is not None and seq > end_seq):
            continue
        players, ball = [], None
        for j in range(starts[i], ends[i]):
            ent = {c: _clean(cols[c][j]) for c in ENTITY_FIELDS}
            if ent["entity_type"] == "ball":
                ball = ent
            else:
                players.append(ent)
        flags = [f for f in (fr.frame_quality_flags or "").split(",") if f]
        yield {
            **base,
            "record_id": f"{match_id}|frame|{int(fr.source_frame_id)}",
            "source_frame_id": int(fr.source_frame_id),
            "period": int(fr.period),
            "source_clock": fr.source_clock,
            "match_elapsed_ms": _clean(fr.match_elapsed_ms),
            "physical_time_ms": _clean(fr.physical_time_ms),
            "source_timestamp": fr.source_timestamp,
            "sequence": seq,
            "quality_flags": flags,
            "possession_team_id": fr.possession_team_id,
            "possession_player_id": fr.possession_player_id,
            "shot_clock_s": _clean(fr.shot_clock_s),
            "ball": ball,
            "players": players,
        }


def roster(match_id: str) -> list[str]:
    d = match_dir(match_id)
    t = pq.read_table(d / "tracking.parquet", columns=["canonical_player_id"])
    return sorted({v for v in t.column(0).to_pylist() if v})
