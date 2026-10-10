"""Team-shape change points: ruptures PELT over 10 s bins of pipeline team-shape series.

Signals are z-scored per team; PELT runs per team and period with an L2 cost, ``min_size`` of four
bins (40 s) and penalty ``PEN_PER_DIM * n_features * log(n_bins)``. Each change point reports the
features whose segment means moved most, in their own units. These are statistical shifts in team
shape; they are not labelled tactical events and there is no ground truth to score them against.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from smip.ml.features import shape_columns, sport_of, team_seconds

MODEL = "shape-change-pelt"
VERSION = "0.1.0"
BIN_S = 10
MIN_BINS = 4
PEN_PER_DIM = 1.5


def detect(session_id: str, match_id: str, t_max: int | None = None) -> dict:
    import ruptures as rpt

    df = team_seconds(session_id, match_id, t_max)
    out: list[dict] = []
    if df.empty:
        return {"model": MODEL, "version": VERSION, "changes": out}
    cols = [c for c in shape_columns(sport_of(match_id)) if c in df and df[c].notna().mean() > 0.5]
    df["bin"] = df["sec"] // BIN_S
    for (team, period), g in df.groupby(["team_id", "period"]):
        b = g.groupby("bin").agg({**dict.fromkeys(cols, "mean"), "t_ms": "min"}).sort_index()
        b[cols] = b[cols].ffill().bfill()
        if len(b) < MIN_BINS * 3 or b[cols].isna().any().any():
            continue
        raw = b[cols].to_numpy(dtype=float)
        sd = raw.std(axis=0)
        sd[sd == 0] = 1.0
        z = (raw - raw.mean(axis=0)) / sd
        pen = PEN_PER_DIM * len(cols) * np.log(len(z))
        bkps = rpt.Pelt(model="l2", min_size=MIN_BINS, jump=1).fit(z).predict(pen=pen)[:-1]
        edges = [0, *bkps, len(z)]
        for n, cp in enumerate(bkps, start=1):
            before, after = slice(edges[n - 1], cp), slice(cp, edges[n + 1])
            dz = z[after].mean(axis=0) - z[before].mean(axis=0)
            draw = raw[after].mean(axis=0) - raw[before].mean(axis=0)
            top = np.argsort(-np.abs(dz))[:3]
            t_cp = int(b["t_ms"].iloc[cp])
            out.append({
                "t_ms": t_cp, "period": int(period), "team_id": team,
                "magnitude_z": round(float(np.linalg.norm(dz)), 2),
                "segment_before_ms": [int(b["t_ms"].iloc[edges[n - 1]]), t_cp],
                "segment_after_ms": [t_cp, int(b["t_ms"].iloc[edges[n + 1] - 1]) + BIN_S * 1000],
                "top_features": [{"feature": cols[i], "delta": round(float(draw[i]), 2),
                                  "before": round(float(raw[before, i].mean()), 2),
                                  "after": round(float(raw[after, i].mean()), 2)} for i in top],
                "evidence_id": f"change:{session_id}:{match_id}:{team}:{t_cp}",
            })
    out.sort(key=lambda r: r["t_ms"])
    return {"model": MODEL, "version": VERSION, "bin_s": BIN_S, "features": cols, "changes": out,
            "note": "statistical shifts in team shape (PELT); not labelled tactical events"}


@lru_cache(maxsize=16)
def _cached(session_id: str, match_id: str, t_bucket: int | None) -> dict:
    return detect(session_id, match_id, None if t_bucket is None else t_bucket * 10_000)


def get_changes(session_id: str, match_id: str, t_max: int | None) -> dict:
    return _cached(session_id, match_id, None if t_max is None else t_max // 10_000)


def summary(ch: dict) -> pd.DataFrame:
    return pd.DataFrame(ch.get("changes", []))
