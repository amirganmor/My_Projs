"""Metrica Sports sample-data adapter (Sample_Game_1/2 CSV format; Game 3 is EPTS/FIFA and not handled here).

Facts verified from the pinned files:
* 25 fps; ``Frame`` is a continuous index across both periods, ``Time [s]`` = Frame * 0.04 with no
  halftime gap. Period 2 of Game 1 starts at frame 71269.
* Coordinates are normalized 0..1 with (0, 0) at the top-left; the README states a 105 x 68 m pitch,
  so meters are ``x_m = (x - 0.5) * 105`` and ``y_m = (0.5 - y) * 68`` (y flipped so +y is "up").
* NaN coordinates mean the player is not on the pitch (substitute) or the ball is out of play.
* Players and teams are anonymized (Player1..Player28, "Home"/"Away"). They stay anonymous: ids are
  namespaced per game because the same label in two games is not known to be the same person.
* No detection flag, possession or confidence is provided.
* Attack direction is not in the files. It is inferred per period from goalkeeper position (the
  player with the most extreme mean x over the first 5 s of the period) and validated against shot
  end locations in the event file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from smip.sources.adapters.common import (
    NormalizedMatch,
    apply_attack_direction,
    gap_segments,
    ns_match,
    ns_player,
    ns_team,
)

log = logging.getLogger(__name__)
SOURCE = "metrica"
FRAME_MS = 40
LENGTH_M, WIDTH_M = 105.0, 68.0


def find_matches(raw_root: Path, revision: str) -> dict[str, Path]:
    base = raw_root / SOURCE / revision / "data"
    if not base.exists():
        return {}
    return {p.name: p for p in sorted(base.iterdir())
            if (p / f"{p.name}_RawTrackingData_Home_Team.csv").exists()
            and (p / f"{p.name}_RawTrackingData_Away_Team.csv").exists()}


def _read_team(path: Path) -> tuple[pd.DataFrame, list[str]]:
    with path.open() as fh:
        fh.readline(), fh.readline()
        header = fh.readline().strip().split(",")
    names, labels = header[:3], []
    for i in range(3, len(header), 2):
        lab = header[i]
        names += [f"{lab}_x", f"{lab}_y"]
        labels.append(lab)
    df = pd.read_csv(path, skiprows=3, header=None, names=names, dtype={"Period": "Int16", "Frame": "int64"})
    return df, labels


def _to_m(x, y):
    return (np.asarray(x, float) - 0.5) * LENGTH_M, (0.5 - np.asarray(y, float)) * WIDTH_M


def normalize(match_dir: Path, revision: str) -> NormalizedMatch:
    mid = match_dir.name
    home_df, home_labels = _read_team(match_dir / f"{mid}_RawTrackingData_Home_Team.csv")
    away_df, away_labels = _read_team(match_dir / f"{mid}_RawTrackingData_Away_Team.csv")
    if not (home_df["Frame"].values == away_df["Frame"].values).all():
        raise ValueError("home/away tracking files are not frame-aligned")
    home_labels = [l for l in home_labels if l != "Ball"]
    away_labels = [l for l in away_labels if l != "Ball"]
    tid = {"Home": ns_team(SOURCE, f"{mid}.home"), "Away": ns_team(SOURCE, f"{mid}.away")}

    def pid(side: str, label: str) -> str:
        return ns_player(SOURCE, f"{mid}.{side.lower()}.{label.replace('Player', '')}")

    df = home_df[["Period", "Frame", "Time [s]"]].copy()
    df = df[df["Period"].notna()].reset_index(drop=True)
    home_df = home_df.loc[home_df["Period"].notna()].reset_index(drop=True)
    away_df = away_df.loc[away_df["Period"].notna()].reset_index(drop=True)
    n = len(df)
    frames = df["Frame"].to_numpy()
    periods = df["Period"].astype(int).to_numpy()
    t_ms = (frames - frames[0]) * FRAME_MS
    period_start = {int(p): int(frames[periods == p][0]) for p in np.unique(periods)}
    offsets = {p: int((f - frames[0]) * FRAME_MS) for p, f in period_start.items()}
    pel = t_ms - np.array([offsets[p] for p in periods])

    # goalkeepers + attack direction per period
    sides = {"Home": (home_df, home_labels), "Away": (away_df, away_labels)}
    gk, sign = {}, {}
    for side, (tdf, labels) in sides.items():
        for p in sorted(period_start):
            first = tdf[(tdf["Period"] == p)].head(125)
            mx = {l: first[f"{l}_x"].mean() for l in labels if first[f"{l}_x"].notna().any()}
            g = max(mx, key=lambda l: abs(mx[l] - 0.5))
            gk.setdefault(side, g)
            sign[(tid[side], p)] = 1.0 if mx[g] < 0.5 else -1.0
    ev_path = match_dir / f"{mid}_RawEventsData.csv"
    ev = pd.read_csv(ev_path) if ev_path.exists() else None
    direction = {"status": "unvalidated", "method": "goalkeeper_position"}
    if ev is not None:
        shots = ev[(ev["Type"] == "SHOT") & ev["End X"].notna()]
        ok = sum(1 for _, r in shots.iterrows()
                 if sign.get((tid[r["Team"]], int(r["Period"])), 0) * (r["End X"] - 0.5) > 0)
        frac = ok / len(shots) if len(shots) else None
        direction = {"status": "validated" if frac is not None and frac >= 0.9 else "conflict",
                     "method": "goalkeeper_position", "validation": "shot end x in attacking half",
                     "agreement_fraction": frac, "shots_checked": len(shots)}

    # long-form tracking
    parts = []
    for side, (tdf, labels) in sides.items():
        for lab in labels:
            x, y = tdf[f"{lab}_x"].to_numpy(float), tdf[f"{lab}_y"].to_numpy(float)
            on = ~np.isnan(x) & ~np.isnan(y)
            idx = np.nonzero(on)[0]
            parts.append(pd.DataFrame({"i": idx, "entity_type": "player", "label": lab, "side": side,
                                       "x_src": x[idx], "y_src": y[idx]}))
    bx, by = home_df["Ball_x"].to_numpy(float), home_df["Ball_y"].to_numpy(float)
    has_ball = ~np.isnan(bx) & ~np.isnan(by)
    bidx = np.nonzero(has_ball)[0]
    parts.append(pd.DataFrame({"i": bidx, "entity_type": "ball", "label": None, "side": None,
                               "x_src": bx[bidx], "y_src": by[bidx]}))
    long = pd.concat(parts, ignore_index=True)
    long["_o"] = (long["entity_type"] != "ball").astype(int)
    long = long.sort_values(["i", "_o", "side", "label"], kind="stable").reset_index(drop=True)
    i = long["i"].to_numpy()
    is_player = (long["entity_type"] == "player").to_numpy()
    team = np.array([tid[s] if s else None for s in long["side"]], dtype=object)
    cpid = np.array([pid(s, l) if s else f"{SOURCE}:ball" for s, l in zip(long["side"], long["label"])], dtype=object)
    x_m, y_m = _to_m(long["x_src"], long["y_src"])
    sgn = np.array([sign.get((t, int(periods[k])), np.nan) if t else np.nan for t, k in zip(team, i)])
    x_att, y_att = apply_attack_direction(x_m, y_m, sgn)
    n_players = np.bincount(i[is_player], minlength=n)
    flags_f = np.where(has_ball, "", "no_ball")
    flags_f = np.where(n_players == 0, np.where(has_ball, "no_entities", "no_ball,no_entities"), flags_f)
    k = len(long)
    tracking = {
        "sequence": i, "source_frame_id": frames[i], "period": periods[i], "source_clock": [None] * k,
        "period_elapsed_ms": pel[i], "match_elapsed_ms": t_ms[i], "physical_time_ms": t_ms[i],
        "source_timestamp": [None] * k, "entity_type": long["entity_type"].to_numpy(),
        "source_player_id": np.array([l if l else None for l in long["label"]], dtype=object),
        "canonical_player_id": cpid, "team_id": team,
        "jersey": np.array([l.replace("Player", "") if l else None for l in long["label"]], dtype=object),
        "x_src": long["x_src"].to_numpy(), "y_src": long["y_src"].to_numpy(), "z_src": np.full(k, np.nan),
        "x_m": x_m, "y_m": y_m, "z_m": np.full(k, np.nan), "x_att": x_att, "y_att": y_att,
        "is_detected": [None] * k, "is_extrapolated": [None] * k, "position_source": ["unknown"] * k,
        "confidence": [None] * k, "possession_team_id": [None] * k, "possession_player_id": [None] * k,
        "frame_quality_flags": flags_f[i],
    }
    frames_tbl = {
        "sequence": np.arange(n), "source_frame_id": frames, "period": periods, "source_clock": [None] * n,
        "period_elapsed_ms": pel, "match_elapsed_ms": t_ms, "physical_time_ms": t_ms, "source_timestamp": [None] * n,
        "shot_clock_s": [None] * n, "n_players": n_players, "n_players_detected": np.zeros(n, int),
        "has_ball": has_ball, "possession_team_id": [None] * n, "possession_player_id": [None] * n,
        "source_segment": [None] * n, "frame_quality_flags": flags_f,
    }

    events = None
    if ev is not None:
        f2i = {int(f): j for j, f in enumerate(frames)}
        sx, sy = _to_m(ev["Start X"], ev["Start Y"])
        ex, ey = _to_m(ev["End X"], ev["End Y"])
        ev_t = [int(t_ms[f2i[int(f)]]) if int(f) in f2i else None for f in ev["Start Frame"]]
        events = {
            "event_id": [f"{SOURCE}:{mid}:ev:{j}" for j in range(len(ev))],
            "match_id": [ns_match(SOURCE, mid)] * len(ev), "period": ev["Period"].astype(int).tolist(),
            "source_clock": ev["Start Time [s]"].astype(str).tolist(), "match_elapsed_ms": ev_t,
            "source_frame_start": ev["Start Frame"].astype("int64").tolist(),
            "source_frame_end": ev["End Frame"].astype("int64").tolist(),
            "event_type": ev["Type"].astype(str).tolist(),
            "event_subtype": ev["Subtype"].where(ev["Subtype"].notna(), None).tolist(),
            "team_id": [tid.get(t) for t in ev["Team"]],
            "player_id": [pid(t, p) if isinstance(p, str) and t in tid else None for t, p in zip(ev["Team"], ev["From"])],
            "x_m": sx.tolist(), "y_m": sy.tolist(), "end_x_m": ex.tolist(), "end_y_m": ey.tolist(),
            "outcome": ev["Subtype"].where(ev["Type"] == "SHOT", None).tolist(),
            "label_origin": ["provider"] * len(ev), "coordinate_space": ["physical_m"] * len(ev),
            "attributes_json": [json.dumps({k: v for k, v in r.items() if pd.notna(v)}, default=str)
                                for r in ev.to_dict("records")],
        }

    players = []
    for side, (tdf, labels) in sides.items():
        for lab in labels:
            col = tdf[f"{lab}_x"]
            on = col.notna()
            players.append({
                "canonical_player_id": pid(side, lab), "source_player_id": lab, "team_id": tid[side],
                "name": f"{side} {lab}", "jersey": lab.replace("Player", ""), "position": None,
                "position_group": None, "is_goalkeeper": lab == gk[side], "goalkeeper_inferred": lab == gk[side],
                "first_frame": int(frames[on.idxmax()]) if on.any() else None,
                "last_frame": int(frames[on[::-1].idxmax()]) if on.any() else None,
            })
    meta = {
        "match_id": ns_match(SOURCE, mid), "source": SOURCE, "source_match_id": mid, "source_revision": revision,
        "sport": "soccer", "competition": "Metrica anonymized sample", "season": None, "date": None,
        "home_team": {"team_id": tid["Home"], "name": f"{mid} Home (anonymized)"},
        "away_team": {"team_id": tid["Away"], "name": f"{mid} Away (anonymized)"},
        "score": None,
        "periods": [{"period": p, "start_frame": f, "end_frame": int(frames[periods == p][-1]),
                     "duration_ms": int((frames[periods == p][-1] - f + 1) * FRAME_MS), "offset_ms": offsets[p],
                     "attack_direction": {tid["Home"]: sign[(tid["Home"], p)], tid["Away"]: sign[(tid["Away"], p)]}}
                    for p, f in sorted(period_start.items())],
        "dimensions": {"length_m": LENGTH_M, "width_m": WIDTH_M, "origin": "centre", "physical": True,
                       "note": "normalized source units scaled by README-stated 105x68 m"},
        "sample_rate_hz": 25,
        "capabilities": {"continuous_tracking": True, "ball": True, "ball_height": False, "events": events is not None,
                         "phases": False, "identity": "anonymized", "detection_flag": False, "possession": "none"},
        "players": players,
        "time_model": {
            "match_elapsed_ms": "(Frame - first Frame) * 40 ms; source frames are continuous, halftime excluded",
            "physical_time_ms": "equal to match_elapsed_ms",
            "source_clock": "not provided (Time [s] is derived from Frame)",
            "window_time_base": "physical_time_ms",
        },
        "coordinate_notes": "0..1 top-left origin converted to meters, origin centre, +y up; x_att/y_att "
                            "rotated per inferred attack direction; ball has no team so x_att is null",
        "direction_validation": direction,
        "anonymized": True,
    }
    quality = {
        "frames": n, "frames_without_entities": int((n_players == 0).sum()),
        "frames_without_ball": int((~has_ball).sum()), "detected_fraction": None,
        "detection_flag": "not provided", "goalkeepers_inferred": gk,
        "missing_segments_over_5s": gap_segments(t_ms, n_players > 0, FRAME_MS, 5000),
    }
    raw_assets = [p for p in match_dir.iterdir() if p.is_file()]
    return NormalizedMatch(meta, frames_tbl, tracking, events, {}, quality, raw_assets)
