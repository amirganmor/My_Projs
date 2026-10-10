"""Deterministic grounded analyst: question -> one typed tool -> templated answer with evidence ids.

The question is treated as data. It is only matched against fixed keyword patterns to pick a tool
and to extract allowlisted arguments (metric enums, team names from match metadata, a clock time).
Nothing from the question reaches SQL or a shell. No language model is required; answers are
templated from tool facts, so every number in an answer is traceable to an evidence id.
"""

from __future__ import annotations

import re
import time
import unicodedata

from smip.analyst import tools
from smip.analyst.tools import Scope, fmt_clock

MAX_QUESTION = 500
INJECTION = re.compile(
    r"ignore (all|any|the|previous|prior)|system prompt|developer message|you are now|jailbreak|"
    r"\b(drop|delete|truncate|insert|alter|update)\b\s+\w+|\brm\s+-|shell|exec\(|;\s*select|<script", re.I)
OUT_OF_SCOPE = re.compile(r"\b(predict|prediction|who will win|bet|betting|odds|injur|salary|transfer|weather)\b", re.I)
CLOCK = re.compile(r"\b(\d{1,3}):(\d{2})\b")
MINUTE = re.compile(r"\b(?:minute|min)\s*(\d{1,3})\b|\b(\d{1,3})(?:'|th minute| min\b)", re.I)
TOP_N = re.compile(r"\btop\s*(\d{1,2})\b", re.I)

TEAM_WORDS = [
    (r"defensive line|line height|high line|deep line|back line", "def_line_height_m"),
    (r"width|wide|narrow", "width_m"),
    (r"depth|compact|stretch|vertical", "depth_m"),
    (r"hull|area|space occupied|spread", "hull_area_m2"),
    (r"centroid|push(ed)? up|territor|block height", "centroid_x"),
]
PLAYER_WORDS = [
    (r"per (active )?min|per minute|work ?rate", "distance_per_active_min_m"),
    (r"sprint", "sprints"),
    (r"fastest|top speed|max(imum)? speed|quickest", "max_speed_mps"),
    (r"high[- ]speed|hsr|high intensity", "hi_distance_m"),
    (r"distance|covered|ran the most|running", "distance_m"),
]
SUPPORTED = [
    "team shape trends (width, depth, hull area, defensive line height, centroid)",
    "top players by distance, high-speed distance, sprints, max speed, distance per active minute",
    "tracking quality gaps and quarantined records",
    "statistically detected team-shape changes",
    "moments most similar to a given clock time",
]


def _clean(q: str) -> str:
    q = unicodedata.normalize("NFKC", q or "")[:MAX_QUESTION]
    return "".join(ch for ch in q if ch.isprintable())


def _team(q: str, match_id: str) -> str | None:
    ql = q.lower()
    hits = [tid for tid, name in tools.teams(match_id).items()
            if name and any(w in ql for w in name.lower().split() if len(w) > 3)]
    return hits[0] if len(hits) == 1 else None


def _clock_ms(q: str) -> int | None:
    if m := CLOCK.search(q):
        return (int(m.group(1)) * 60 + int(m.group(2))) * 1000
    if m := MINUTE.search(q):
        return int(m.group(1) or m.group(2)) * 60_000
    return None


def route(q: str, match_id: str) -> tuple[str, dict] | None:
    ql = q.lower()
    team = _team(q, match_id)
    if re.search(r"quality|gap|missing|reliab|trust|insufficient|coverage|quarantin|extrapolat", ql):
        return "quality_gaps", {}
    if re.search(r"similar|resembl|like (this|that|the) moment|look(ed)? like", ql):
        return "similar_moments", {"t_ms": _clock_ms(q)}
    team_metric = next((m for pat, m in TEAM_WORDS if re.search(pat, ql)), None)
    player_metric = next((m for pat, m in PLAYER_WORDS if re.search(pat, ql)), None)
    if re.search(r"\bplayers?\b|\bwho\b", ql) or (player_metric and not team_metric):
        n = int(m.group(1)) if (m := TOP_N.search(q)) else 5
        return "top_players", {"metric": player_metric or "distance_m", "n": n, "team_id": team}
    if team_metric:
        return "team_shape_trend", {"metric": team_metric, "team_id": team}
    if re.search(r"chang|shift|switch|adjust|transition|shape", ql):
        return "shape_changes", {"team_id": team}
    return None


def _refuse(scope: Scope | None, reason: str, t0: float, mode: str) -> dict:
    return {"answer": "I can only answer questions my read-only tools support.", "observations": [],
            "limitations": [], "refused": True, "refusal_reason": reason, "supported": SUPPORTED,
            "mode": mode, "method": "deterministic tool routing", "generator": "template",
            "time_range": [0, scope.as_of_ms if scope else None], "tools_called": [],
            "latency_ms": round((time.time() - t0) * 1000, 1)}


def cutoff(session_id: str, match_id: str, mode: str, as_of_ms: int | None) -> int | None:
    from smip.serving import ch

    rows = ch.query_rows("SELECT stats FROM stream_stats WHERE session_id={s:String} AND match_id={m:String} "
                         "ORDER BY emitted_at DESC LIMIT 1", {"s": session_id, "m": match_id},
                         settings=tools.QUERY_SETTINGS)
    if not rows:
        return None
    import json

    cur = json.loads(rows[0]["stats"]).get("cursor_t")
    if cur is None:
        return None
    return cur if mode == "post_match" or as_of_ms is None else min(cur, int(as_of_ms))


def ask(question: str, session_id: str, match_id: str, mode: str = "replay_time",
        as_of_ms: int | None = None) -> dict:
    t0 = time.time()
    q = _clean(question)
    if not q.strip():
        return _refuse(None, "empty question", t0, mode)
    if INJECTION.search(q):
        return _refuse(None, "the question contains instructions or commands; the analyst only runs its "
                             "fixed read-only tools", t0, mode)
    if OUT_OF_SCOPE.search(q):
        return _refuse(None, "predictions, betting, injuries and off-pitch topics are outside the data", t0, mode)
    cut = cutoff(session_id, match_id, mode, as_of_ms)
    if cut is None:
        return _refuse(None, "no processed data for this session yet", t0, mode)
    scope = Scope(session_id, match_id, cut, mode)
    routed = route(q, match_id)
    if routed is None:
        return _refuse(scope, "no tool matches this question", t0, mode)
    name, args = routed
    if name == "similar_moments" and args.get("t_ms") is None:
        args["t_ms"] = cut
    args = {k: v for k, v in args.items() if v is not None}
    try:
        res = tools.TOOLS[name](scope, **args)
    except ValueError as exc:
        return _refuse(scope, str(exc), t0, mode)
    headline = {
        "team_shape_trend": "Team shape over time, first vs latest bucket before the cutoff:",
        "top_players": "Player ranking from final and partial 60 s windows before the cutoff:",
        "quality_gaps": "Where the tracking data is too thin to judge:",
        "shape_changes": "Largest statistically detected shifts in team shape:",
        "similar_moments": f"Moments whose 10 s team shape most resembles {fmt_clock(args.get('t_ms'))}:",
    }[name]
    return {
        "answer": headline if res.facts else "No qualifying data before the cutoff.",
        "observations": [{"statement": f["statement"], "evidence_ids": f["evidence_ids"], "value": f.get("value")}
                         for f in res.facts],
        "limitations": res.limitations, "refused": False, "refusal_reason": None,
        "mode": mode, "method": "deterministic tool routing", "generator": "template",
        "time_range": [0, cut], "tools_called": [{"tool": name, "args": args}],
        "data": res.data, "latency_ms": round((time.time() - t0) * 1000, 1),
    }
