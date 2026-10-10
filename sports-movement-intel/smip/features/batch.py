"""Batch (offline, in-order) execution of the shared engine over a normalized match.

Used for backfills and as the reference side of batch/stream parity checks. Uses exactly the same
``MatchEngine`` code path as the streaming job; only the input ordering/chunking differs.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from smip.features.context import context_from_meta, sport_config
from smip.features.engine import MatchEngine
from smip.features.hooks import hooks_for
from smip.replay.frames import iter_frames, load_meta


def run_match(match_id: str, session_id: str = "batch", chunk: int = 500,
              messages: list[dict] | None = None, keep: set[str] | None = None) -> dict[str, pd.DataFrame]:
    """``keep`` limits which output kinds are retained (per-position ``obs`` rows dominate memory)."""
    meta = load_meta(match_id)
    ctx = context_from_meta(meta)
    cfg = sport_config(meta["sport"])
    eng = MatchEngine(session_id, ctx, cfg, frame_hooks=hooks_for(meta["sport"]))
    out: dict[str, list] = defaultdict(list)

    def collect(res: dict) -> None:
        for k, v in res.items():
            if keep is None or k in keep:
                out[k].extend(v)

    buf: list[dict] = []
    src = messages if messages is not None else iter_frames(match_id)
    for fr in src:
        buf.append(fr)
        if len(buf) >= chunk:
            collect(eng.ingest(buf))
            buf = []
    buf.append({"end_of_stream": True, "sequence": 2**62})
    collect(eng.ingest(buf))
    return {k: pd.DataFrame(v) for k, v in out.items()}


def final_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["is_final"]].reset_index(drop=True) if "is_final" in df else df
