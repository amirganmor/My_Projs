"""Read-only typed analyst tools over pipeline outputs.

Every tool takes validated arguments (enum metrics, allowlisted team/entity ids), runs a fixed SQL
template with bound parameters under ``readonly=2``, a 5 s timeout and a row cap, and never reads
data past ``as_of_ms``. Each returned fact carries an evidence id that names the table and key it
came from, so an answer can be traced back to rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

from smip.serving import ch
from smip.serving.catalog import match_meta

QUERY_SETTINGS = {"readonly": 2, "prefer_column_name_to_alias": 1, "max_execution_time": 5, "max_result_rows": 5000, "result_overflow_mode": "throw"}

TeamMetric = Literal["width_m", "depth_m", "hull_area_m2", "def_line_height_m", "centroid_x"]
PlayerMetric = Literal["distance_m", "hi_distance_m", "sprints", "max_speed_mps", "distance_per_active_min_m"]
TEAM_METRICS: tuple[str, ...] = TeamMetric.__args__
PLAYER_METRICS: tuple[str, ...] = PlayerMetric.__args__
METRIC_LABEL = {
    "width_m": "team width (m)", "depth_m": "team depth (m)", "hull_area_m2": "convex hull area (m²)",
    "def_line_height_m": "defensive line height (m from own goal line)", "centroid_x": "team centroid x (m, attack-normalized)",
    "distance_m": "distance (m)", "hi_distance_m": "high-speed distance (m)", "sprints": "sprints",
    "max_speed_mps": "max speed (m/s)", "distance_per_active_min_m": "distance per active minute (m)",
}
UNIT = {"distance_m": "m", "hi_distance_m": "m", "sprints": "sprints", "max_speed_mps": "m/s",
        "distance_per_active_min_m": "m/min"}


@dataclass
class Scope:
    session_id: str
    match_id: str
    as_of_ms: int            # hard cutoff; tools never read past it
    mode: str

    @property
    def params(self) -> dict:
        return {"s": self.session_id, "m": self.match_id, "cut": self.as_of_ms}


@dataclass
class ToolResult:
    tool: str
    facts: list[dict] = field(default_factory=list)       # {statement, value, evidence_ids}
    data: dict = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


def _q(sql: str, params: dict) -> list[dict]:
    return ch.query_rows(sql, params, settings=QUERY_SETTINGS)


def teams(match_id: str) -> dict[str, str]:
    m = match_meta(match_id)
    return {m["home_team"]["team_id"]: m["home_team"]["name"], m["away_team"]["team_id"]: m["away_team"]["name"]}


def fmt_clock(ms: int | None) -> str:
    if ms is None:
        return "–"
    s = int(ms // 1000)
    return f"{s // 60}:{s % 60:02d}"


def _check_team(scope: Scope, team_id: str | None) -> str | None:
    if team_id is not None and team_id not in teams(scope.match_id):
        raise ValueError("team_id not in this match")
    return team_id


# ------------------------------------------------------------------ tools
def team_shape_trend(scope: Scope, metric: TeamMetric = "width_m", team_id: str | None = None,
                     bucket_min: int = 10) -> ToolResult:
    if metric not in TEAM_METRICS:
        raise ValueError("metric not allowed")
    _check_team(scope, team_id)
    bucket_min = max(1, min(int(bucket_min), 45))
    rows = _q(
        f"SELECT team_id, intDiv(window_start_ms, {bucket_min * 60000}) AS b, min(window_start_ms) AS t0, "
        f"max(window_end_ms) AS t1, avg(mean_{metric}) AS v, sum(n_sufficient) AS n "
        "FROM team_windows FINAL WHERE session_id={s:String} AND match_id={m:String} "
        "AND window_end_ms <= {cut:Int64} AND n_sufficient > 0 GROUP BY team_id, b ORDER BY team_id, b",
        scope.params)
    names = teams(scope.match_id)
    res = ToolResult("team_shape_trend", data={"metric": metric, "bucket_min": bucket_min, "series": rows})
    by_team: dict[str, list[dict]] = {}
    for r in rows:
        if team_id is None or r["team_id"] == team_id:
            by_team.setdefault(r["team_id"], []).append(r)
    for tm, rs in by_team.items():
        if len(rs) < 2:
            res.limitations.append(f"{names[tm]}: fewer than two {bucket_min}-min buckets before the cutoff")
            continue
        a, b = rs[0], rs[-1]
        delta = b["v"] - a["v"]
        res.facts.append({
            "statement": f"{names[tm]} {METRIC_LABEL[metric]}: {a['v']:.1f} in {fmt_clock(a['t0'])}–{fmt_clock(a['t1'])} "
                         f"→ {b['v']:.1f} in {fmt_clock(b['t0'])}–{fmt_clock(b['t1'])} ({delta:+.1f})",
            "value": round(delta, 2), "team_id": tm,
            "evidence_ids": [f"team_windows:{tm}:t={a['t0']}", f"team_windows:{tm}:t={b['t0']}"],
        })
    res.limitations.append("window means over frames with enough outfield players; attack-normalized coordinates")
    return res


def top_players(scope: Scope, metric: PlayerMetric = "distance_m", n: int = 5, team_id: str | None = None) -> ToolResult:
    if metric not in PLAYER_METRICS:
        raise ValueError("metric not allowed")
    _check_team(scope, team_id)
    n = max(1, min(int(n), 10))
    p = {**scope.params, "tm": team_id or ""}
    rows = _q(
        "SELECT entity_id, any(team_id) AS team, sum(distance_m) AS distance_m, sum(hi_distance_m) AS hi_distance_m, "
        "sum(sprint_count) AS sprints, max(max_speed_mps) AS max_speed_mps, sum(active_ms) AS active_ms, "
        "min(window_start_ms) AS t0 "
        "FROM player_windows FINAL WHERE session_id={s:String} AND match_id={m:String} "
        "AND window_end_ms <= {cut:Int64} AND ({tm:String} = '' OR team_id = {tm:String}) "
        "GROUP BY entity_id HAVING sum(active_ms) > 0", p)
    for r in rows:
        r["team_id"] = r.pop("team")
        r["distance_per_active_min_m"] = r["distance_m"] / (r["active_ms"] / 60000)
    min_active = 10 * 60000 if metric == "distance_per_active_min_m" else 0
    rows = sorted((r for r in rows if r["active_ms"] >= min_active), key=lambda r: -r[metric])[:n]
    meta = {p["canonical_player_id"]: p for p in match_meta(scope.match_id).get("players", [])}
    names = teams(scope.match_id)
    res = ToolResult("top_players", data={"metric": metric, "rows": rows})
    for i, r in enumerate(rows, 1):
        pm = meta.get(r["entity_id"], {})
        who = pm.get("name") or r["entity_id"]
        res.facts.append({
            "statement": f"{i}. {who} ({names.get(r['team_id'], r['team_id'])}) — {r[metric]:.1f} {UNIT[metric]}"
                         f" over {r['active_ms'] / 60000:.1f} active min",
            "value": round(float(r[metric]), 2), "entity_id": r["entity_id"],
            "evidence_ids": [f"player_windows:{r['entity_id']}"],
        })
    if min_active:
        res.limitations.append("players with < 10 active minutes excluded from per-minute ranking")
    res.limitations.append("distance uses causal EMA-smoothed positions and excludes gaps > max_gap_ms")
    return res


def quality_gaps(scope: Scope) -> ToolResult:
    from smip.replay.frames import match_dir

    qf = match_dir(scope.match_id) / "quality.json"
    q = json.loads(qf.read_text()) if qf.exists() else {}
    segs = [s for s in q.get("missing_segments_over_5s", []) if (s.get("start_ms") or 0) <= scope.as_of_ms]
    quar = _q("SELECT reason, count() AS n FROM quarantine WHERE session_id={s:String} "
              "AND match_id={m:String} GROUP BY reason ORDER BY n DESC", scope.params)
    low = _q("SELECT team_id, window_start_ms AS t0, window_end_ms AS t1, n_frames, n_sufficient "
             "FROM team_windows FINAL WHERE session_id={s:String} AND match_id={m:String} "
             "AND window_end_ms <= {cut:Int64} AND n_frames > 0 AND n_sufficient < 0.8 * n_frames "
             "ORDER BY t0 LIMIT 20", scope.params)
    gaps = _q("SELECT sum(excluded_gap_ms) AS excluded_ms, sum(active_ms) AS active_ms, "
              "sum(active_ms - detected_ms) AS undetected_ms FROM player_windows FINAL "
              "WHERE session_id={s:String} AND match_id={m:String} AND window_end_ms <= {cut:Int64}", scope.params)
    res = ToolResult("quality_gaps", data={"missing_segments": segs, "quarantine": quar, "low_coverage_windows": low,
                                           "player_time": gaps[0] if gaps else {}})
    names = teams(scope.match_id)
    if segs:
        total = sum(s["duration_ms"] for s in segs)
        res.facts.append({"statement": f"{len(segs)} tracking gaps longer than 5 s before the cutoff, "
                                       f"{total / 1000:.0f} s in total", "value": total,
                          "evidence_ids": ["quality:missing_segments_over_5s"]})
    for s in sorted(segs, key=lambda s: -s["duration_ms"])[:3]:
        res.facts.append({"statement": f"longest gap: no tracking for {s['duration_ms'] / 1000:.0f} s from "
                                       f"{fmt_clock(s['start_ms'])}",
                          "value": s["duration_ms"], "evidence_ids": [f"quality:missing:t={s['start_ms']}"]})
    for w in low[:5]:
        res.facts.append({"statement": f"{names.get(w['team_id'], w['team_id'])}: only {w['n_sufficient']}/{w['n_frames']} "
                                       f"frames with enough outfield players in {fmt_clock(w['t0'])}–{fmt_clock(w['t1'])}",
                          "value": w["n_sufficient"] / w["n_frames"],
                          "evidence_ids": [f"team_windows:{w['team_id']}:t={w['t0']}"]})
    g = gaps[0] if gaps else {}
    if g.get("active_ms"):
        res.facts.append({"statement": f"{g['undetected_ms'] / g['active_ms']:.0%} of player time is provider-extrapolated "
                                       f"(not directly detected); {g['excluded_ms'] / 1000:.0f} s excluded as gaps",
                          "value": g["undetected_ms"] / g["active_ms"], "evidence_ids": ["player_windows:detected_ms"]})
    for r in quar:
        res.facts.append({"statement": f"{r['n']} records quarantined: {r['reason']}", "value": r["n"],
                          "evidence_ids": [f"quarantine:{r['reason']}"]})
    if not res.facts:
        res.facts.append({"statement": "no quality gaps detected before the cutoff", "value": 0, "evidence_ids": []})
    return res


def shape_changes(scope: Scope, team_id: str | None = None, top: int = 5) -> ToolResult:
    from smip.ml.changes import get_changes

    _check_team(scope, team_id)
    ch_ = get_changes(scope.session_id, scope.match_id, scope.as_of_ms if scope.mode == "replay_time" else None)
    rows = [c for c in ch_["changes"] if c["segment_after_ms"][1] <= scope.as_of_ms + 10_000 or scope.mode != "replay_time"]
    rows = [c for c in rows if c["t_ms"] <= scope.as_of_ms and (team_id is None or c["team_id"] == team_id)]
    rows = sorted(rows, key=lambda c: -c["magnitude_z"])[:max(1, min(top, 10))]
    names = teams(scope.match_id)
    res = ToolResult("shape_changes", data={"changes": rows, "model": ch_["model"], "version": ch_["version"]})
    for c in sorted(rows, key=lambda c: c["t_ms"]):
        f0 = c["top_features"][0]
        res.facts.append({"statement": f"{fmt_clock(c['t_ms'])} {names.get(c['team_id'], c['team_id'])}: "
                                       f"{METRIC_LABEL.get(f0['feature'], f0['feature'])} {f0['before']:.1f} → {f0['after']:.1f}"
                                       f" (shift {c['magnitude_z']:.1f} σ)",
                          "value": c["magnitude_z"], "evidence_ids": [f"change:{c['team_id']}:t={c['t_ms']}"]})
    res.limitations.append(ch_["note"])
    return res


def similar_moments(scope: Scope, t_ms: int, k: int = 5) -> ToolResult:
    from smip.ml.moments import get_index, similar

    t_ms = min(int(t_ms), scope.as_of_ms)
    idx = get_index(scope.session_id, scope.match_id, scope.as_of_ms if scope.mode == "replay_time" else None)
    res = ToolResult("similar_moments")
    if idx is None or len(idx) < 10:
        res.limitations.append("not enough processed data to build the moment index yet")
        return res
    out = similar(idx, t_ms, max(1, min(k, 10)))
    out["neighbours"] = [n for n in out["neighbours"] if n["t_ms"] <= scope.as_of_ms]
    res.data = out
    names = teams(scope.match_id)
    for n in out["neighbours"]:
        who = names.get(n["possession_label"] or "", "no clear possession")
        res.facts.append({"statement": f"{fmt_clock(n['t_ms'])} (period {n['period']}) similarity {n['similarity']:.2f}; "
                                       f"possession: {who}", "value": n["similarity"],
                          "evidence_ids": [f"moment:t={n['t_ms']}"]})
    res.limitations.append(out["note"])
    return res


TOOLS = {"team_shape_trend": team_shape_trend, "top_players": top_players, "quality_gaps": quality_gaps,
         "shape_changes": shape_changes, "similar_moments": similar_moments}
