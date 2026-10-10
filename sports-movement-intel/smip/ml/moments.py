"""Similar moments: k-nearest neighbours over 10 s team-shape vectors.

A moment is anchored every ``STEP_S`` seconds of game time. Its vector is, for each team in a fixed
order, the mean of each shape feature over the causal 10 s window plus its trend (last 3 s minus
first 3 s), z-scored per match. Neighbours closer than ``EXCLUDE_S`` in the same period are removed so
retrieval cannot trivially return the adjacent seconds.

Evaluation (``evaluate``): possession-state lift. Each moment is labelled with the team holding a
>= 60 % possession share over its last 3 s. Lift = P(neighbour label == query label) / P(two random
labelled moments share a label). Lift > 1 means shape vectors carry game-state information; it does
not mean the moments are tactically equivalent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from smip.ml.features import shape_columns, sport_of, team_seconds

MODEL = "similar-moments-knn"
VERSION = "0.1.0"
WINDOW_S = 10
STEP_S = 2
EXCLUDE_S = 30
MIN_SECONDS = 8
POSS_THRESHOLD = 0.6


@dataclass
class MomentIndex:
    session_id: str
    match_id: str
    teams: list[str]
    columns: list[str]
    t_ms: np.ndarray
    period: np.ndarray
    sec: np.ndarray
    X: np.ndarray            # z-scored vectors
    raw: pd.DataFrame        # per-anchor raw team means for explanation
    label: list[str | None]
    built_at: float

    def __len__(self) -> int:
        return len(self.t_ms)


def _label(win: pd.DataFrame, teams: list[str]) -> str | None:
    last = win[win["sec"] > win["sec"].max() - 3]
    for tm in teams:
        share = last.loc[last["team_id"] == tm, "poss_share"].mean()
        if pd.notna(share) and share >= POSS_THRESHOLD:
            return tm
    return None


def build_index(session_id: str, match_id: str, t_max: int | None = None) -> MomentIndex | None:
    df = team_seconds(session_id, match_id, t_max)
    if df.empty:
        return None
    cols = list(shape_columns(sport_of(match_id)))
    cols = [c for c in cols if c in df and df[c].notna().mean() > 0.5]
    teams = sorted(df["team_id"].unique().tolist())
    if len(teams) != 2 or not cols:
        return None
    rows, vecs, labels = [], [], []
    for period, pdf in df.groupby("period"):
        wide = pdf.pivot_table(index="sec", columns="team_id", values=cols + ["poss_share"])
        secs = wide.index.to_numpy()
        tms = pdf.groupby("sec")["t_ms"].min()
        for s in range(int(secs.min()) + WINDOW_S - 1, int(secs.max()) + 1, STEP_S):
            w = wide.loc[(wide.index > s - WINDOW_S) & (wide.index <= s)]
            if len(w) < MIN_SECONDS:
                continue
            v, rawrow = [], {}
            for tm in teams:
                for c in cols:
                    series = w[(c, tm)] if (c, tm) in w else pd.Series(dtype=float)
                    m = series.mean()
                    trend = series.tail(3).mean() - series.head(3).mean()
                    v += [m, trend]
                    rawrow[f"{tm}|{c}"] = None if pd.isna(m) else round(float(m), 2)
            if np.isnan(v).mean() > 0.25:
                continue
            win_long = pdf[(pdf["sec"] > s - WINDOW_S) & (pdf["sec"] <= s)]
            labels.append(_label(win_long, teams))
            vecs.append(v)
            rows.append({"t_ms": int(tms.get(s, s * 1000)), "period": int(period), "sec": s, **rawrow})
    if not vecs:
        return None
    X = np.asarray(vecs, dtype=float)
    mu, sd = np.nanmean(X, axis=0), np.nanstd(X, axis=0)
    sd[~np.isfinite(sd) | (sd == 0)] = 1.0
    X = np.nan_to_num((X - mu) / sd)
    raw = pd.DataFrame(rows)
    return MomentIndex(session_id, match_id, teams, cols, raw["t_ms"].to_numpy(), raw["period"].to_numpy(),
                       raw["sec"].to_numpy(), X, raw, labels, time.time())


@lru_cache(maxsize=16)
def _cached(session_id: str, match_id: str, t_bucket: int | None) -> MomentIndex | None:
    return build_index(session_id, match_id, None if t_bucket is None else t_bucket * 10_000)


def get_index(session_id: str, match_id: str, t_max: int | None) -> MomentIndex | None:
    """Replay-time callers pass the processed cursor; it is bucketed to 10 s to bound rebuilds."""
    return _cached(session_id, match_id, None if t_max is None else t_max // 10_000)


def _neighbours(idx: MomentIndex, i: int, k: int) -> list[int]:
    d = np.linalg.norm(idx.X - idx.X[i], axis=1)
    near = (idx.period == idx.period[i]) & (np.abs(idx.sec - idx.sec[i]) < EXCLUDE_S)
    d[near] = np.inf
    kept: list[int] = []
    for j in np.argsort(d):
        if not np.isfinite(d[j]) or len(kept) == k:
            break
        # one result per moment: suppress anchors within EXCLUDE_S of an already chosen neighbour
        if any(idx.period[j] == idx.period[m] and abs(idx.sec[j] - idx.sec[m]) < EXCLUDE_S for m in kept):
            continue
        kept.append(int(j))
    return kept


def similar(idx: MomentIndex, t_ms: int, k: int = 5) -> dict:
    i = int(np.clip(np.searchsorted(idx.t_ms, t_ms, side="right") - 1, 0, len(idx) - 1))
    nb = _neighbours(idx, i, k)
    d = np.linalg.norm(idx.X[nb] - idx.X[i], axis=1) if nb else np.array([])
    scale = float(np.median(np.linalg.norm(idx.X - idx.X.mean(axis=0), axis=1))) or 1.0

    def moment(j: int) -> dict:
        r = idx.raw.iloc[j].to_dict()
        return {"t_ms": int(idx.t_ms[j]), "period": int(idx.period[j]), "possession_label": idx.label[j],
                "evidence_id": f"moment:{idx.session_id}:{idx.match_id}:{int(idx.t_ms[j])}",
                "shape": {tm: {c: r.get(f"{tm}|{c}") for c in idx.columns} for tm in idx.teams}}

    return {"model": MODEL, "version": VERSION, "query": moment(i),
            "neighbours": [{**moment(j), "distance": round(float(dist), 3),
                            "similarity": round(float(np.exp(-dist / scale)), 3)} for j, dist in zip(nb, d)],
            "index_size": len(idx), "window_s": WINDOW_S, "exclusion_s": EXCLUDE_S, "features": idx.columns,
            "note": "geometric similarity of team shape over 10 s; not tactical equivalence"}


def evaluate(idx: MomentIndex, k: int = 5) -> dict:
    lab = np.array([x if x is not None else "" for x in idx.label])
    labelled = np.where(lab != "")[0]
    if len(labelled) < 20:
        return {"model": MODEL, "version": VERSION, "status": "insufficient_labels", "labelled": int(len(labelled))}
    _, counts = np.unique(lab[labelled], return_counts=True)
    p = counts / counts.sum()
    baseline = float((p ** 2).sum())
    hits = total = 0
    for i in labelled:
        nb = [j for j in _neighbours(idx, int(i), k * 3) if lab[j]][:k]
        hits += sum(int(lab[j] == lab[i]) for j in nb)
        total += len(nb)
    precision = hits / total if total else 0.0
    circular = sport_of(idx.match_id) == "basketball"
    return {"model": MODEL, "version": VERSION, "k": k, "moments": len(idx), "labelled": int(len(labelled)),
            "label_source": "heuristic offense from positions" if circular else "provider possession",
            "valid_evidence": not circular,
            "caveat": ("label is derived from player positions (>=60% in attacking half), which the centroid "
                       "feature also encodes; this lift is circular and is not evidence of quality") if circular else None,
            "precision_same_possession": round(precision, 3), "random_baseline": round(baseline, 3),
            "lift": round(precision / baseline, 3) if baseline else None,
            "method": "leave-local-out (+-30 s) kNN; label = team with >=60% possession share in last 3 s"}
