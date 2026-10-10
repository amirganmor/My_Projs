"""NBA SportVU (2015-16 archive) adapter.

Facts verified from the pinned files:
* Each .7z holds one ``<gameid>.json`` with ``events``; each event carries ``moments`` =
  ``[period, epoch_ms, game_clock_remaining_s, shot_clock_s, null, [[team_id, player_id, x, y, z], ...]]``.
  The ball is ``team_id = -1``. Units are feet on a 94 x 50 ft court with the origin at a corner.
* Consecutive events overlap: the same moment (same epoch_ms) appears in several events. For game
  0021500492, 211,445 moments reduce to 79,963 unique timestamps with zero conflicting duplicates.
  Policy: deduplicate by epoch_ms, keep the first occurrence, count conflicts (content mismatch) in
  quality.json and keep the first copy.
* Nominal 25 Hz (40 ms). Moments exist only inside plays: dead balls, timeouts and breaks between
  periods are not captured (gaps), and the game clock stops while tracking continues.
* No possession, detection flag or confidence field.

Time model: ``physical_time_ms`` = epoch_ms - first epoch_ms (monotonic sensor time, used for
kinematics and windows); ``match_elapsed_ms`` = elapsed game clock (stalls when the clock stops;
those frames are flagged ``clock_stopped``); ``source_clock`` = remaining game clock string.
Attack direction is inferred per period (defense sits between the offense and the basket it
protects in half-court frames) and checked for the halftime switch.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from smip.config import get_settings
from smip.sources.adapters.common import NormalizedMatch, apply_attack_direction, ns_match, ns_player, ns_team
from smip.sources.safe_extract import extract_7z

log = logging.getLogger(__name__)
SOURCE = "sportvu"
FT = 0.3048
LENGTH_FT, WIDTH_FT = 94.0, 50.0
BASKET_FT = 5.25          # basket centre from baseline


def _period_len_s(p: int) -> int:
    return 720 if p <= 4 else 300


def find_matches(raw_root: Path, revision: str) -> dict[str, Path]:
    base = raw_root / SOURCE / revision / "data" / "2016.NBA.Raw.SportVU.Game.Logs"
    return {p.stem: p for p in sorted(base.glob("*.7z"))} if base.exists() else {}


def _load(archive: Path) -> tuple[dict, Path]:
    dest = get_settings().data_dir / "extracted" / SOURCE / archive.stem
    files = sorted(dest.glob("*.json")) if dest.exists() else []
    if not files:
        files = [p for p in extract_7z(archive, dest) if p.suffix == ".json"]
    return json.loads(files[0].read_text()), files[0]


def _clock_str(sec: float | None) -> str | None:
    if sec is None:
        return None
    m, s = divmod(float(sec), 60)
    return f"{int(m):02d}:{s:05.2f}"


def _infer_direction(frames: list, periods: np.ndarray, home: int, away: int) -> tuple[dict, dict]:
    """Per period: in half-court frames (all 10 players in one half), the team closer on average to
    that half's basket is defending it, so the other team attacks it."""
    votes = {}
    for (per, ents) in frames:
        pl = [e for e in ents if e[0] in (home, away)]
        if len(pl) < 10:
            continue
        xs = np.array([e[2] for e in pl])
        if (xs < 47).all():
            basket = BASKET_FT
        elif (xs > 47).all():
            basket = LENGTH_FT - BASKET_FT
        else:
            continue
        d = {t: np.mean([abs(e[2] - basket) for e in pl if e[0] == t]) for t in (home, away)}
        offense = home if d[home] > d[away] else away
        attacks_plus = basket > 47
        v = votes.setdefault(per, [0, 0])      # [home attacks +x, home attacks -x]
        v[0 if (offense == home) == attacks_plus else 1] += 1
    sign, detail = {}, {}
    for per, (a, b) in sorted(votes.items()):
        s = 1.0 if a >= b else -1.0
        sign[per] = s
        detail[per] = {"home_attacks_plus_x_votes": a, "home_attacks_minus_x_votes": b,
                       "agreement": round(max(a, b) / (a + b), 3)}
    halves_ok = (sign.get(1) == sign.get(2) and sign.get(3) == sign.get(4) and sign.get(1) == -sign.get(3, 0)
                 if all(p in sign for p in (1, 2, 3, 4)) else None)
    return sign, {"method": "half-court defender proximity", "per_period": detail,
                  "halftime_switch_consistent": halves_ok,
                  "status": "validated" if halves_ok and min(d["agreement"] for d in detail.values()) > 0.6
                  else "low_confidence"}


def normalize(archive: Path, revision: str) -> NormalizedMatch:
    g, json_path = _load(archive)
    gid = str(g["gameid"])
    ev0 = g["events"][0]
    home, visitor = ev0["home"], ev0["visitor"]
    home_id, away_id = int(home["teamid"]), int(visitor["teamid"])
    tid = {home_id: ns_team(SOURCE, home_id), away_id: ns_team(SOURCE, away_id)}

    players = {}
    for ev in g["events"]:
        for side in ("home", "visitor"):
            team = ev[side]
            for p in team.get("players", []):
                players.setdefault(p["playerid"], {
                    "canonical_player_id": ns_player(SOURCE, p["playerid"]), "source_player_id": str(p["playerid"]),
                    "team_id": tid[int(team["teamid"])], "name": f"{p['firstname']} {p['lastname']}",
                    "jersey": p.get("jersey"), "position": p.get("position"), "position_group": None,
                    "is_goalkeeper": False})

    seen: dict[int, tuple] = {}
    conflicts, total = 0, 0
    for ev in g["events"]:
        for m in ev["moments"]:
            total += 1
            key = int(m[1])
            if key in seen:
                if seen[key][0] != m[0] or [e[:4] for e in seen[key][4]] != [e[:4] for e in m[5]]:
                    conflicts += 1
                continue
            seen[key] = (int(m[0]), m[2], m[3], ev["eventId"], m[5])
    keys = sorted(seen)
    periods = np.array([seen[k][0] for k in keys])
    if (np.diff(periods) < 0).any():
        raise ValueError("period decreases with epoch time; archive ordering assumption violated")
    epoch = np.array(keys, dtype=np.int64)
    t_ms = epoch - epoch[0]
    period_start = {int(p): int(t_ms[periods == p][0]) for p in np.unique(periods)}
    sign, direction = _infer_direction([(seen[k][0], seen[k][4]) for k in keys[::5]], periods, home_id, away_id)
    base_game = {p: sum(_period_len_s(q) for q in range(1, p)) * 1000 for p in period_start}

    fr = {k: [] for k in ("sequence", "source_frame_id", "period", "source_clock", "period_elapsed_ms",
                          "match_elapsed_ms", "physical_time_ms", "source_timestamp", "shot_clock_s", "n_players",
                          "n_players_detected", "has_ball", "possession_team_id", "possession_player_id",
                          "source_segment", "frame_quality_flags")}
    tr = {k: [] for k in ("sequence", "source_frame_id", "period", "source_clock", "period_elapsed_ms",
                          "match_elapsed_ms", "physical_time_ms", "source_timestamp", "entity_type",
                          "source_player_id", "canonical_player_id", "team_id", "jersey", "x_src", "y_src", "z_src",
                          "possession_team_id", "possession_player_id", "frame_quality_flags")}
    prev_clock, stopped = None, 0
    unknown = set()
    for seq, k in enumerate(keys):
        per, gclock, sclock, evid, ents = seen[k]
        t = int(t_ms[seq])
        mel = None if gclock is None else base_game[per] + int(round((_period_len_s(per) - gclock) * 1000))
        flags = []
        if gclock is not None and prev_clock is not None and prev_clock[0] == per and gclock == prev_clock[1]:
            flags.append("clock_stopped")
            stopped += 1
        prev_clock = (per, gclock)
        has_ball = any(e[0] == -1 for e in ents)
        if not has_ball:
            flags.append("no_ball")
        n_pl = sum(1 for e in ents if e[0] != -1)
        if n_pl < 10:
            flags.append("few_players")
        fl = ",".join(flags)
        clock = _clock_str(gclock)
        for kk, v in (("sequence", seq), ("source_frame_id", k), ("period", per), ("source_clock", clock),
                      ("period_elapsed_ms", t - period_start[per]), ("match_elapsed_ms", mel), ("physical_time_ms", t),
                      ("source_timestamp", str(k)), ("shot_clock_s", sclock), ("n_players", n_pl),
                      ("n_players_detected", 0), ("has_ball", has_ball), ("possession_team_id", None),
                      ("possession_player_id", None), ("source_segment", str(evid)), ("frame_quality_flags", fl)):
            fr[kk].append(v)
        for e in sorted(ents, key=lambda e: (e[0] != -1, e[0], e[1])):
            team, pid, x, y, z = e[:5]
            is_ball = team == -1
            if not is_ball and pid not in players:
                unknown.add(pid)
            for kk, v in (("sequence", seq), ("source_frame_id", k), ("period", per), ("source_clock", clock),
                          ("period_elapsed_ms", t - period_start[per]), ("match_elapsed_ms", mel),
                          ("physical_time_ms", t), ("source_timestamp", str(k)),
                          ("entity_type", "ball" if is_ball else "player"),
                          ("source_player_id", None if is_ball else str(pid)),
                          ("canonical_player_id", f"{SOURCE}:ball" if is_ball else ns_player(SOURCE, pid)),
                          ("team_id", None if is_ball else tid.get(int(team))),
                          ("jersey", None if is_ball else (players.get(pid) or {}).get("jersey")),
                          ("x_src", x), ("y_src", y), ("z_src", z if is_ball else None),
                          ("possession_team_id", None), ("possession_player_id", None), ("frame_quality_flags", fl)):
                tr[kk].append(v)

    x = np.array(tr["x_src"], float)
    y = np.array(tr["y_src"], float)
    z = np.array([np.nan if v is None else v for v in tr["z_src"]], float)
    x_m, y_m, z_m = (x - LENGTH_FT / 2) * FT, (y - WIDTH_FT / 2) * FT, z * FT
    per_arr = np.array(tr["period"])
    teams = np.array(tr["team_id"], dtype=object)
    s_home = np.array([sign.get(int(p), np.nan) for p in per_arr])
    sgn = np.where(teams == tid[home_id], s_home, np.where(teams == tid[away_id], -s_home, np.nan))
    x_att, y_att = apply_attack_direction(x_m, y_m, sgn)
    n = len(x)
    tr.update(x_m=x_m, y_m=y_m, z_m=z_m, x_att=x_att, y_att=y_att, z_src=z, is_detected=[None] * n,
              is_extrapolated=[None] * n, position_source=["unknown"] * n, confidence=[None] * n)

    times = np.array(fr["physical_time_ms"])
    meta = {
        "match_id": ns_match(SOURCE, gid), "source": SOURCE, "source_match_id": gid, "source_revision": revision,
        "sport": "basketball", "competition": "NBA", "season": "2015-16", "date": g.get("gamedate"),
        "home_team": {"team_id": tid[home_id], "name": home["name"], "abbreviation": home.get("abbreviation"),
                      "nba_team_id": home_id},
        "away_team": {"team_id": tid[away_id], "name": visitor["name"], "abbreviation": visitor.get("abbreviation"),
                      "nba_team_id": away_id},
        "score": None,
        "periods": [{"period": p, "offset_ms": off, "duration_ms": int(t_ms[periods == p][-1] - off + 40),
                     "game_clock_length_s": _period_len_s(p),
                     "attack_direction": {tid[home_id]: sign.get(p, float("nan")), tid[away_id]: -sign.get(p, float("nan"))}}
                    for p, off in sorted(period_start.items())],
        "dimensions": {"length_m": LENGTH_FT * FT, "width_m": WIDTH_FT * FT, "origin": "centre", "physical": True,
                       "source_units": "feet, origin at a corner"},
        "sample_rate_hz": 25,
        "capabilities": {"continuous_tracking": "within plays only", "ball": True, "ball_height": True,
                         "events": False, "phases": False, "identity": "named", "detection_flag": False,
                         "possession": "none (heuristic offense in spacing metrics)"},
        "players": list(players.values()),
        "nba_game_id": gid,
        "time_model": {
            "physical_time_ms": "source epoch ms minus first moment (sensor time; used for kinematics/windows)",
            "match_elapsed_ms": "elapsed game clock; stalls while the clock is stopped (flag clock_stopped)",
            "source_clock": "remaining game clock MM:SS.ss as provided",
            "window_time_base": "physical_time_ms, period-relative",
            "gaps": "dead balls/timeouts between plays are not tracked; replay compresses gaps > 2 s for scheduling only",
        },
        "coordinate_notes": "feet (corner origin) -> meters (centre origin); x_att/y_att rotated per inferred direction",
        "direction_validation": direction,
    }
    quality = {
        "moments_total": total, "unique_moments": len(keys), "duplicate_moments_dropped": total - len(keys),
        "conflicting_duplicates": conflicts, "frames_clock_stopped": stopped,
        "frames_without_ball": int(sum(1 for b in fr["has_ball"] if not b)),
        "frames_few_players": int(sum(1 for c in fr["n_players"] if c < 10)),
        "unknown_player_ids": sorted(unknown), "detected_fraction": None, "detection_flag": "not provided",
        "missing_segments_over_5s": [{"start_ms": int(a), "end_ms": int(b), "duration_ms": int(b - a)}
                                     for a, b in zip(times[:-1], times[1:]) if b - a >= 5000],
    }
    return NormalizedMatch(meta, fr, tr, None, {}, quality, [archive])
