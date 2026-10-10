"""SYNTHETIC TEST FIXTURES - not real match data.

Generates a small normalized soccer match with analytically known motion (players on circles at
constant speed) so engine metrics can be checked against closed-form values. Written through the
same ``write_normalized`` path as real adapters, under a temporary SMIP_DATA_DIR.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from smip.sources.adapters.common import NormalizedMatch, write_normalized

SOURCE = "synthetic"
FRAME_MS = 100
PERIOD_S = 150
RADIUS_M = 8.0
LENGTH_M, WIDTH_M = 105.0, 68.0


def player_speed(j: int) -> float:
    return 1.5 + 0.5 * (j % 6)      # 1.5 .. 4.0 m/s


def build(tmp: Path, match: str = "m1", gap_player: int = 0, gap_s: tuple[float, float] = (40.0, 43.0)) -> str:
    """Two periods x PERIOD_S seconds, 2 teams x 11 players + ball. Player ``gap_player`` is absent
    during ``gap_s`` of period 1 (a real tracking gap)."""
    raw = tmp / "raw" / SOURCE / match
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "SYNTHETIC.txt").write_text("synthetic test fixture; not real data\n")
    teams = [f"{SOURCE}:team:home", f"{SOURCE}:team:away"]
    players = []
    for ti, team in enumerate(teams):
        for k in range(11):
            j = ti * 11 + k
            players.append({"canonical_player_id": f"{SOURCE}:player:{j}", "source_player_id": str(j), "team_id": team,
                            "name": f"Synthetic {j}", "jersey": str(k + 1), "position": "GK" if k == 0 else None,
                            "position_group": None, "is_goalkeeper": k == 0})
    fr = {k: [] for k in ("sequence", "source_frame_id", "period", "source_clock", "period_elapsed_ms",
                          "match_elapsed_ms", "physical_time_ms", "source_timestamp", "shot_clock_s", "n_players",
                          "n_players_detected", "has_ball", "possession_team_id", "possession_player_id",
                          "source_segment", "frame_quality_flags")}
    tr = {k: [] for k in ("sequence", "source_frame_id", "period", "source_clock", "period_elapsed_ms",
                          "match_elapsed_ms", "physical_time_ms", "source_timestamp", "entity_type",
                          "source_player_id", "canonical_player_id", "team_id", "jersey", "x_src", "y_src", "z_src",
                          "x_m", "y_m", "z_m", "x_att", "y_att", "is_detected", "is_extrapolated", "position_source",
                          "confidence", "possession_team_id", "possession_player_id", "frame_quality_flags")}
    n_per = PERIOD_S * 1000 // FRAME_MS
    seq = 0
    for period in (1, 2):
        for i in range(n_per):
            pel = i * FRAME_MS
            t = (period - 1) * PERIOD_S * 1000 + pel
            poss = teams[(t // 10000) % 2]
            ents = [("ball", None, f"{SOURCE}:ball", None, None, 0.0, 0.0, True)]
            for j, p in enumerate(players):
                if j == gap_player and period == 1 and gap_s[0] * 1000 <= pel < gap_s[1] * 1000:
                    continue
                cx = -30.0 + (j % 11) * 6.0
                cy = -20.0 if j < 11 else 20.0
                w = player_speed(j) / RADIUS_M
                a = w * t / 1000.0
                ents.append(("player", p["source_player_id"], p["canonical_player_id"], p["team_id"], p["jersey"],
                             cx + RADIUS_M * math.cos(a), cy + RADIUS_M * math.sin(a), j % 3 != 0))
            n_pl = len(ents) - 1
            n_det = sum(1 for e in ents[1:] if e[7])
            for k, v in (("sequence", seq), ("source_frame_id", seq), ("period", period), ("source_clock", None),
                         ("period_elapsed_ms", pel), ("match_elapsed_ms", t), ("physical_time_ms", t),
                         ("source_timestamp", None), ("shot_clock_s", None), ("n_players", n_pl),
                         ("n_players_detected", n_det), ("has_ball", True), ("possession_team_id", poss),
                         ("possession_player_id", None), ("source_segment", None), ("frame_quality_flags", "")):
                fr[k].append(v)
            for et, spid, cpid, team, jer, x, y, det in ents:
                sign = 1.0 if (team == teams[0]) == (period == 1) else -1.0
                if team is None:
                    sign = 1.0 if poss == teams[0] else -1.0
                for k, v in (("sequence", seq), ("source_frame_id", seq), ("period", period), ("source_clock", None),
                             ("period_elapsed_ms", pel), ("match_elapsed_ms", t), ("physical_time_ms", t),
                             ("source_timestamp", None), ("entity_type", et), ("source_player_id", spid),
                             ("canonical_player_id", cpid), ("team_id", team), ("jersey", jer), ("x_src", x),
                             ("y_src", y), ("z_src", None), ("x_m", x), ("y_m", y), ("z_m", None),
                             ("x_att", x * sign), ("y_att", y * sign), ("is_detected", det),
                             ("is_extrapolated", not det), ("position_source", "observed" if det else "provider_extrapolated"),
                             ("confidence", None), ("possession_team_id", poss), ("possession_player_id", None),
                             ("frame_quality_flags", "")):
                    tr[k].append(v)
            seq += 1
    for k in ("z_src", "z_m", "confidence"):
        tr[k] = np.array([np.nan if v is None else v for v in tr[k]], dtype=float)
    meta = {
        "match_id": f"{SOURCE}:{match}", "source": SOURCE, "source_match_id": match, "source_revision": "synthetic-1",
        "sport": "soccer", "competition": "SYNTHETIC", "season": None, "date": None,
        "home_team": {"team_id": teams[0], "name": "Synthetic Home"},
        "away_team": {"team_id": teams[1], "name": "Synthetic Away"},
        "periods": [{"period": p, "offset_ms": (p - 1) * PERIOD_S * 1000, "duration_ms": PERIOD_S * 1000,
                     "attack_direction": {teams[0]: 1.0 if p == 1 else -1.0, teams[1]: -1.0 if p == 1 else 1.0}}
                    for p in (1, 2)],
        "dimensions": {"length_m": LENGTH_M, "width_m": WIDTH_M, "origin": "centre", "physical": True},
        "sample_rate_hz": 10, "capabilities": {"continuous_tracking": True, "synthetic": True},
        "players": players,
        "time_model": {"physical_time_ms": "synthetic"}, "coordinate_notes": "synthetic",
    }
    nm = NormalizedMatch(meta, fr, tr, None, {}, {"synthetic": True}, [raw / "SYNTHETIC.txt"])
    write_normalized(nm, tmp / "normalized", tmp / "raw")
    return meta["match_id"]
