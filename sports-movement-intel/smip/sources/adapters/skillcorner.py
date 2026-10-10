"""SkillCorner Open Data adapter (tracking_extrapolated.jsonl + match.json + dynamic events + phases).

Facts verified from the pinned files (see docs/DATA_SOURCES.md):
* 10 fps; ``frame`` is a video frame index; ``timestamp`` is the conventional match clock
  (period 2 starts at "00:45:00.00"); ``period`` is null before kick-off.
* Coordinates are meters with origin at the pitch centre; pitch_length/pitch_width in match.json.
* ``is_detected`` false means the provider extrapolated the position (no confidence score given).
* Some frames carry no player data (e.g. broadcast replays); they are retained as frames with the
  ``no_entities`` flag so downstream gap logic sees them.
* ``home_team_side[i]`` gives the home team's attacking direction in period i+1; validated against
  phases_of_play ``attacking_side`` of the team in possession.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

from smip.sources.adapters.common import (
    NormalizedMatch,
    apply_attack_direction,
    gap_segments,
    ns_match,
    ns_player,
    ns_team,
)

log = logging.getLogger(__name__)
SOURCE = "skillcorner"
FRAME_MS = 100


def _clock_to_ms(ts: str | None) -> int | None:
    if not ts:
        return None
    h, m, s = ts.split(":")
    return int(round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000))


def find_matches(raw_root: Path, revision: str) -> dict[str, Path]:
    base = raw_root / SOURCE / revision / "data" / "matches"
    return {p.name: p for p in sorted(base.iterdir()) if (p / f"{p.name}_match.json").exists()
            and (p / f"{p.name}_tracking_extrapolated.jsonl").exists()} if base.exists() else {}


def _direction_check(phases: pd.DataFrame | None, home_id: int, home_sides: list[str]) -> dict:
    if phases is None or phases.empty or "attacking_side" not in phases:
        return {"status": "unvalidated", "reason": "no phases_of_play"}
    agree = total = 0
    for p, side in enumerate(home_sides, start=1):
        sub = phases[phases["period"] == p]
        if sub.empty:
            continue
        home_rows = sub[sub["team_in_possession_id"] == home_id]
        away_rows = sub[sub["team_in_possession_id"] != home_id]
        other = "right_to_left" if side == "left_to_right" else "left_to_right"
        agree += int((home_rows["attacking_side"] == side).sum() + (away_rows["attacking_side"] == other).sum())
        total += len(sub)
    frac = agree / total if total else None
    return {"status": "validated" if frac is not None and frac > 0.99 else "conflict",
            "agreement_fraction": frac, "phases_checked": total}


def normalize(match_dir: Path, revision: str) -> NormalizedMatch:
    mid = match_dir.name
    meta_raw = json.loads((match_dir / f"{mid}_match.json").read_text())
    home, away = meta_raw["home_team"], meta_raw["away_team"]
    home_tid, away_tid = ns_team(SOURCE, home["id"]), ns_team(SOURCE, away["id"])
    home_sides: list[str] = meta_raw["home_team_side"]
    periods_meta = {p["period"]: p for p in meta_raw["match_periods"]}

    players_meta = {}
    for p in meta_raw["players"]:
        role = p.get("player_role") or {}
        players_meta[p["id"]] = {
            "canonical_player_id": ns_player(SOURCE, p["id"]),
            "source_player_id": str(p["id"]),
            "team_id": ns_team(SOURCE, p["team_id"]),
            "name": p.get("short_name"),
            "jersey": str(p.get("number")) if p.get("number") is not None else None,
            "position": role.get("acronym"),
            "position_group": role.get("position_group"),
            "is_goalkeeper": role.get("acronym") == "GK" or role.get("position_group") == "Goalkeeper",
            "start_time": p.get("start_time"),
            "end_time": p.get("end_time"),
        }

    # attack sign per (team, period): +1 attacks toward +x
    sign = {}
    for i, side in enumerate(home_sides, start=1):
        s = 1.0 if side == "left_to_right" else -1.0
        sign[(home_tid, i)], sign[(away_tid, i)] = s, -s

    # Period offsets use max(metadata end_frame, last observed frame) so physical time stays monotonic
    # even if tracking runs past the metadata boundary. Halftime is excluded.
    frame_re = re.compile(r'"frame":\s*(\d+).*?"period":\s*(\d+|null)')
    observed_end: dict[int, int] = {}
    with (match_dir / f"{mid}_tracking_extrapolated.jsonl").open() as fh:
        for line in fh:
            m = frame_re.search(line)
            if m and m.group(2) != "null":
                p = int(m.group(2))
                observed_end[p] = max(observed_end.get(p, 0), int(m.group(1)))
    offsets, acc, period_end = {}, 0, {}
    for p in sorted(periods_meta):
        offsets[p] = acc
        period_end[p] = max(periods_meta[p]["end_frame"], observed_end.get(p, 0))
        acc += (period_end[p] - periods_meta[p]["start_frame"] + 1) * FRAME_MS

    fr: dict[str, list] = {k: [] for k in (
        "sequence", "source_frame_id", "period", "source_clock", "period_elapsed_ms", "match_elapsed_ms",
        "physical_time_ms", "source_timestamp", "shot_clock_s", "n_players", "n_players_detected", "has_ball",
        "possession_team_id", "possession_player_id", "source_segment", "frame_quality_flags")}
    tr: dict[str, list] = {k: [] for k in (
        "sequence", "source_frame_id", "period", "source_clock", "period_elapsed_ms", "match_elapsed_ms",
        "physical_time_ms", "source_timestamp", "entity_type", "source_player_id", "canonical_player_id",
        "team_id", "jersey", "x_src", "y_src", "z_src", "is_detected", "possession_team_id",
        "possession_player_id", "frame_quality_flags")}
    dropped_no_period = 0
    unknown_players: set = set()
    seq = 0
    last_frame = None
    non_monotonic = 0
    with (match_dir / f"{mid}_tracking_extrapolated.jsonl").open() as fh:
        for line in fh:
            d = json.loads(line)
            period = d.get("period")
            if period is None or period not in periods_meta:
                dropped_no_period += 1
                continue
            frame = int(d["frame"])
            if last_frame is not None and frame <= last_frame:
                non_monotonic += 1
                continue
            last_frame = frame
            pel = (frame - periods_meta[period]["start_frame"]) * FRAME_MS
            mel = offsets[period] + pel
            clock = d.get("timestamp")
            poss = d.get("possession") or {}
            group = poss.get("group")
            poss_team = home_tid if group == "home team" else away_tid if group == "away team" else None
            poss_player = ns_player(SOURCE, poss.get("player_id"))
            flags = []
            ball = d.get("ball_data") or {}
            has_ball = ball.get("x") is not None and ball.get("y") is not None
            if not has_ball:
                flags.append("no_ball")
            pdata = d.get("player_data") or []
            if not pdata:
                flags.append("no_entities")
            n_det = sum(1 for p in pdata if p.get("is_detected"))
            if pdata and n_det < len(pdata):
                flags.append("provider_extrapolated")
            fl = ",".join(flags)
            for k, v in (("sequence", seq), ("source_frame_id", frame), ("period", period), ("source_clock", clock),
                         ("period_elapsed_ms", pel), ("match_elapsed_ms", mel), ("physical_time_ms", mel),
                         ("source_timestamp", None), ("shot_clock_s", None), ("n_players", len(pdata)),
                         ("n_players_detected", n_det), ("has_ball", has_ball), ("possession_team_id", poss_team),
                         ("possession_player_id", poss_player), ("source_segment", None),
                         ("frame_quality_flags", fl)):
                fr[k].append(v)
            rows = []
            if has_ball:
                rows.append(("ball", None, f"{SOURCE}:ball", None, None, ball["x"], ball["y"], ball.get("z"),
                             ball.get("is_detected")))
            for p in pdata:
                pm = players_meta.get(p["player_id"])
                if pm is None:
                    unknown_players.add(p["player_id"])
                rows.append(("player", str(p["player_id"]), ns_player(SOURCE, p["player_id"]),
                             pm["team_id"] if pm else None, pm["jersey"] if pm else None,
                             p.get("x"), p.get("y"), None, p.get("is_detected")))
            for et, spid, cpid, tid, jer, x, y, z, det in rows:
                for k, v in (("sequence", seq), ("source_frame_id", frame), ("period", period),
                             ("source_clock", clock), ("period_elapsed_ms", pel), ("match_elapsed_ms", mel),
                             ("physical_time_ms", mel), ("source_timestamp", None), ("entity_type", et),
                             ("source_player_id", spid), ("canonical_player_id", cpid), ("team_id", tid),
                             ("jersey", jer), ("x_src", x), ("y_src", y), ("z_src", z), ("is_detected", det),
                             ("possession_team_id", poss_team), ("possession_player_id", poss_player),
                             ("frame_quality_flags", fl)):
                    tr[k].append(v)
            seq += 1

    x = np.array(tr["x_src"], dtype=float)
    y = np.array(tr["y_src"], dtype=float)
    z = np.array([np.nan if v is None else v for v in tr["z_src"]], dtype=float)
    per = np.array(tr["period"])
    teams = np.array(tr["team_id"], dtype=object)
    etype = np.array(tr["entity_type"], dtype=object)
    poss_t = np.array(tr["possession_team_id"], dtype=object)
    ref_team = np.where(etype == "ball", poss_t, teams)
    sgn = np.array([sign.get((t, p), np.nan) if t is not None else np.nan for t, p in zip(ref_team, per)])
    x_att, y_att = apply_attack_direction(x, y, sgn)
    det = np.array([None if v is None else bool(v) for v in tr["is_detected"]], dtype=object)
    tr.update(
        x_m=x, y_m=y, z_m=z, x_att=x_att, y_att=y_att,
        is_extrapolated=[None if v is None else (not v) for v in det],
        position_source=["unknown" if v is None else ("observed" if v else "provider_extrapolated") for v in det],
        confidence=[None] * len(x),
    )
    tr["z_src"] = z

    # events + phases
    events = None
    ev_path = match_dir / f"{mid}_dynamic_events.csv"
    if ev_path.exists():
        ev = pd.read_csv(ev_path, low_memory=False)
        fs = ev["frame_start"].astype("Int64")
        frame_to_mel = dict(zip(fr["source_frame_id"], fr["match_elapsed_ms"]))
        events = {
            "event_id": [f"{SOURCE}:{mid}:ev:{e}" for e in ev["event_id"]],
            "match_id": [ns_match(SOURCE, mid)] * len(ev),
            "period": ev["period"].astype("Int64").tolist(),
            "source_clock": ev["time_start"].astype(str).tolist(),
            "match_elapsed_ms": [frame_to_mel.get(int(f)) if pd.notna(f) else None for f in fs],
            "source_frame_start": fs.tolist(),
            "source_frame_end": ev["frame_end"].astype("Int64").tolist(),
            "event_type": ev["event_type"].astype(str).tolist(),
            "event_subtype": ev["event_subtype"].where(ev["event_subtype"].notna(), None).tolist(),
            "team_id": [ns_team(SOURCE, int(t)) if pd.notna(t) else None for t in ev["team_id"]],
            "player_id": [ns_player(SOURCE, int(p)) if pd.notna(p) else None for p in ev["player_id"]],
            "x_m": ev["x_start"].tolist(), "y_m": ev["y_start"].tolist(),
            "end_x_m": ev["x_end"].tolist(), "end_y_m": ev["y_end"].tolist(),
            "outcome": (ev["pass_outcome"] if "pass_outcome" in ev else pd.Series([None] * len(ev)))
            .where(lambda s: s.notna(), None).tolist(),
            "label_origin": ["provider_derived"] * len(ev),
            "coordinate_space": ["physical_m"] * len(ev),
            "attributes_json": [json.dumps({k: v for k, v in r.items() if pd.notna(v)}, default=str)
                                for r in ev.to_dict("records")],
        }
    phases = None
    ph_path = match_dir / f"{mid}_phases_of_play.csv"
    if ph_path.exists():
        phases = pd.read_csv(ph_path)
    direction = _direction_check(phases, home["id"], home_sides)
    extra = {}
    if phases is not None:
        ph = phases.copy()
        ph["match_id"] = ns_match(SOURCE, mid)
        ph["team_in_possession_id"] = ph["team_in_possession_id"].map(lambda t: ns_team(SOURCE, int(t)) if pd.notna(t) else None)
        ph["label_origin"] = "provider_derived"
        extra["phases"] = pa.Table.from_pandas(ph, preserve_index=False)

    times = np.array(fr["physical_time_ms"])
    has_players = np.array(fr["n_players"]) > 0
    comp = meta_raw.get("competition_edition") or {}
    meta = {
        "match_id": ns_match(SOURCE, mid),
        "source": SOURCE,
        "source_match_id": mid,
        "source_revision": revision,
        "sport": "soccer",
        "competition": (comp.get("competition") or {}).get("name"),
        "season": (comp.get("season") or {}).get("name"),
        "date": meta_raw.get("date_time"),
        "home_team": {"team_id": home_tid, "name": home.get("short_name") or home.get("name")},
        "away_team": {"team_id": away_tid, "name": away.get("short_name") or away.get("name")},
        "score": {"home": meta_raw.get("home_team_score"), "away": meta_raw.get("away_team_score")},
        "periods": [{"period": p, "start_frame": pm["start_frame"], "end_frame": pm["end_frame"],
                     "observed_end_frame": period_end[p],
                     "duration_ms": (period_end[p] - pm["start_frame"] + 1) * FRAME_MS,
                     "offset_ms": offsets[p],
                     "attack_direction": {home_tid: sign[(home_tid, p)], away_tid: sign[(away_tid, p)]}}
                    for p, pm in sorted(periods_meta.items())],
        "dimensions": {"length_m": float(meta_raw["pitch_length"]), "width_m": float(meta_raw["pitch_width"]),
                       "origin": "centre", "physical": True},
        "sample_rate_hz": 10,
        "capabilities": {"continuous_tracking": True, "ball": True, "ball_height": True, "events": events is not None,
                         "phases": phases is not None, "identity": "named", "detection_flag": True,
                         "possession": "provider"},
        "players": list(players_meta.values()),
        "time_model": {
            "match_elapsed_ms": "cumulative in-period time from observed period start frames; halftime excluded",
            "physical_time_ms": "equal to match_elapsed_ms (10 fps video frames)",
            "source_clock": "conventional match clock string as provided (period 2 starts at 45:00)",
            "window_time_base": "physical_time_ms",
        },
        "coordinate_notes": "source meters, origin centre; x_att/y_att rotated so team attacks +x "
                            "(ball uses provider possession team; null when unknown)",
        "direction_validation": direction,
    }
    quality = {
        "dropped_frames_without_period": dropped_no_period,
        "non_monotonic_frames_dropped": non_monotonic,
        "frames": len(fr["sequence"]),
        "frames_without_entities": int((~has_players).sum()),
        "frames_without_ball": int(sum(1 for b in fr["has_ball"] if not b)),
        "detected_fraction": float(np.mean([bool(v) for v in det if v is not None])) if len(det) else None,
        "unknown_player_ids": sorted(unknown_players),
        "missing_segments_over_5s": gap_segments(times, has_players, FRAME_MS, 5000),
    }
    raw_assets = [p for p in match_dir.iterdir() if p.is_file()]
    return NormalizedMatch(meta, fr, tr, events, extra, quality, raw_assets)
