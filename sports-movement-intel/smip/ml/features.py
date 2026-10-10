"""Per-second team-shape series read from pipeline output (ClickHouse ``team_frames``).

Seconds are bucketed on physical game time so soccer (10 Hz) and NBA (25 Hz) share one resolution.
Only frames with ``sufficient`` players contribute to shape features; possession is the share of
frames where the team was in possession (provider possession when present).
"""

from __future__ import annotations

import pandas as pd

from smip.serving import ch

SHAPE = ("width_m", "depth_m", "hull_area_m2", "def_line_height_m", "centroid_x")
BASKETBALL_SHAPE = ("spacing_hull_m2", "mean_pairwise_m", "paint_count", "corner_count")


def team_seconds(session_id: str, match_id: str, t_max: int | None = None) -> pd.DataFrame:
    """Rows: team_id, period, sec, t_ms (second start), shape means, poss_share, n."""
    cond = "" if t_max is None else " AND t_ms <= {tmax:Int64}"
    rows = ch.query_rows(
        "SELECT team_id, period, intDiv(t_ms, 1000) AS sec, min(t_ms) AS t0_ms, count() AS n, "
        "avgIf(width_m, sufficient) AS width_m, avgIf(depth_m, sufficient) AS depth_m, "
        "avgIf(hull_area_m2, sufficient) AS hull_area_m2, avgIf(def_line_height_m, sufficient) AS def_line_height_m, "
        "avgIf(centroid_x, sufficient) AS centroid_x, avgIf(spacing_hull_m2, sufficient) AS spacing_hull_m2, "
        "avgIf(mean_pairwise_m, sufficient) AS mean_pairwise_m, avg(paint_count) AS paint_count, "
        "avg(corner_count) AS corner_count, "
        "avg(toFloat64(ifNull(in_possession, offense))) AS poss_share "
        "FROM team_frames FINAL WHERE session_id={s:String} AND match_id={m:String}" + cond +
        " GROUP BY team_id, period, sec ORDER BY team_id, period, sec",
        {"s": session_id, "m": match_id, "tmax": t_max or 0})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.rename(columns={"t0_ms": "t_ms"})
    return df.astype(dict.fromkeys(SHAPE + BASKETBALL_SHAPE + ("poss_share",), "float64"), errors="ignore")


def sport_of(match_id: str) -> str:
    return "basketball" if match_id.startswith("sportvu:") else "soccer"


def shape_columns(sport: str) -> tuple[str, ...]:
    if sport == "basketball":
        return ("width_m", "depth_m", "hull_area_m2", "centroid_x") + BASKETBALL_SHAPE
    return SHAPE
