"""NBA court geometry and per-frame spacing metrics (hook for the shared engine).

Coordinates are attack-normalized meters (origin at court centre, the team attacks +x). Court
geometry follows the NBA rulebook: 94x50 ft court, basket centre 5.25 ft from the baseline,
16 ft wide lane extending 19 ft from the baseline, 22 ft corner three measured from the basket
within 14 ft of the baseline.
"""

from __future__ import annotations

import math

import numpy as np

from smip.features.engine import hull_area

FT = 0.3048
COURT_L, COURT_W = 94 * FT, 50 * FT
BASKET_X = COURT_L / 2 - 5.25 * FT
LANE_HALF_W, LANE_DEPTH = 8 * FT, 19 * FT
CORNER_Y, CORNER_DEPTH = 22 * FT, 14 * FT


def in_paint(xa: float, ya: float) -> bool:
    return xa >= COURT_L / 2 - LANE_DEPTH and abs(ya) <= LANE_HALF_W


def in_corner(xa: float, ya: float) -> bool:
    return xa >= COURT_L / 2 - CORNER_DEPTH and abs(ya) >= CORNER_Y


def spacing_hook(fr: dict, team: str, players: list, ctx) -> dict:
    """Offense is the team in provider possession, else the team whose players are mostly in their
    attacking half (heuristic, SportVU has no possession field). Defensive teams get ball pressure."""
    pts = np.array([[p[1], p[2]] for p in players]) if players else np.zeros((0, 2))
    out = {"spacing_hull_m2": None, "mean_pairwise_m": None, "paint_count": None, "corner_count": None,
           "nearest_def_to_ball_m": None, "offense": None}
    if len(pts) < 2:
        return out
    offense = fr["poss"] == team if fr.get("poss") is not None else bool((pts[:, 0] > 0).mean() >= 0.6)
    d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
    out.update(offense=offense, mean_pairwise_m=round(float(d[np.triu_indices(len(pts), 1)].mean()), 3),
               spacing_hull_m2=hull_area(pts))
    if offense:
        out["paint_count"] = int(sum(in_paint(x, y) for x, y in pts))
        out["corner_count"] = int(sum(in_corner(x, y) for x, y in pts))
    else:
        ball = next((e for e in fr["ents"] if e[1] == "ball" and e[3] is not None), None)
        own = [(e[3], e[4]) for e in fr["ents"] if e[1] == "player" and e[2] == team and e[3] is not None]
        if ball is not None and own:
            out["nearest_def_to_ball_m"] = round(min(math.hypot(x - ball[3], y - ball[4]) for x, y in own), 3)
    return out
