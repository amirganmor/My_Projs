"""FastAPI service: catalog, replay control, pipeline-served frames/metrics, health, analyst.

Every number returned under /api/sessions/* is read from ClickHouse tables written by the Spark
streaming job (lineage: replay -> Kafka -> Spark -> ClickHouse). Nothing is recomputed here from
normalized files, except the catalog/metadata.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from smip.serving import ch
from smip.serving.catalog import list_matches, match_meta

app = FastAPI(title="SMIP API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])

ID_RE = re.compile(r"^[A-Za-z0-9:_\-|.]{1,160}$")
REPLAY_BADGE = "HISTORICAL MATCH REPLAY"


def _id(v: str, name: str = "id") -> str:
    if not ID_RE.match(v or ""):
        raise HTTPException(400, f"invalid {name}")
    return v


def _public() -> bool:
    from smip.config import get_settings

    return get_settings().public_demo


def _redistributable() -> set[str]:
    return {m["match_id"] for m in list_matches() if m["redistributable_demo"]}


def _public_guard(match_id: str) -> str:
    """Public demo mode serves only redistributable (MIT SkillCorner) matches; others look absent."""
    _id(match_id)
    if _public() and match_id not in _redistributable():
        raise HTTPException(404, "unknown match")
    return match_id


# ------------------------------------------------------------------ catalog
@app.get("/api/health")
def health():
    try:
        ch.query_rows("SELECT 1 AS ok")
        ok = True
    except Exception as exc:  # noqa: BLE001
        return {"status": "degraded", "clickhouse": str(exc)}
    return {"status": "ok", "clickhouse": ok}


@app.get("/api/catalog")
def catalog():
    ms = list_matches()
    if _public():
        ms = [m for m in ms if m["redistributable_demo"]]
    return {"badge": REPLAY_BADGE, "public_demo": _public(), "matches": ms}


@app.get("/api/matches/{match_id}")
def match(match_id: str):
    try:
        return match_meta(_public_guard(match_id))
    except FileNotFoundError:
        raise HTTPException(404, "unknown match") from None


# ------------------------------------------------------------------- replay
class StartReplay(BaseModel):
    match_id: str
    speed: float = Field(1.0, ge=0, le=100)
    seed: int = 7
    faults: dict = Field(default_factory=dict)


@app.post("/api/sessions")
def start_session(req: StartReplay):
    from smip.replay.service import send_control
    from smip.replay.session import FaultConfig, new_session_id

    _public_guard(req.match_id)
    match_meta(req.match_id)
    faults = FaultConfig(**req.faults).validate()
    sid = new_session_id(req.match_id)
    send_control("start", sid, match_id=req.match_id, speed=req.speed, seed=req.seed, faults=asdict(faults))
    return {"session_id": sid, "match_id": req.match_id, "badge": REPLAY_BADGE}


class Control(BaseModel):
    command: str = Field(pattern="^(pause|resume|speed|stop)$")
    speed: float | None = Field(None, ge=0, le=100)


@app.post("/api/sessions/{session_id}/control")
def control(session_id: str, req: Control):
    from smip.replay.service import send_control

    return send_control(req.command, _id(session_id), speed=req.speed)


@app.get("/api/sessions")
def sessions(match_id: str | None = None, limit: int = Query(50, le=500)):
    where = "WHERE match_id = {m:String}" if match_id else ""
    rows = ch.query_rows(
        f"SELECT session_id, match_id, source, sport, speed, status, frames_sent, last_seq, started_at, updated_at, "
        f"faults, note FROM replay_sessions FINAL {where} ORDER BY updated_at DESC LIMIT {int(limit)}",
        {"m": match_id} if match_id else None)
    if _public():
        ok = _redistributable()
        rows = [r for r in rows if r["match_id"] in ok]
    return rows


@app.get("/api/sessions/{session_id}/cursor")
def cursor(session_id: str, match_id: str):
    _public_guard(match_id)
    rows = ch.query_rows(
        "SELECT stats, emitted_at FROM stream_stats WHERE session_id={s:String} AND match_id={m:String} "
        "ORDER BY emitted_at DESC LIMIT 1", {"s": _id(session_id), "m": _id(match_id)})
    if not rows:
        return {"cursor_t": None, "ended": False}
    st = json.loads(rows[0]["stats"])
    st["emitted_at"] = rows[0]["emitted_at"]
    return st


def _cursor_t(session_id: str, match_id: str, mode: str, t_to: int | None) -> int | None:
    """Replay-time mode never serves data past the processed cursor."""
    if mode == "post_match":
        return t_to
    c = cursor(session_id, match_id).get("cursor_t")
    if c is None:
        return -1
    return c if t_to is None else min(c, t_to)


# ------------------------------------------------------------------- frames
@app.get("/api/sessions/{session_id}/frames")
def frames(session_id: str, match_id: str, from_seq: int = 0, from_t: int | None = None,
           limit: int = Query(300, le=3000)):
    """Compact frame chunk from pipeline output: {seq:[...], t:[...], ents:[[id,type,team,x,y,det,speed]...]}.

    ``from_t`` seeks by physical game time (ms) instead of sequence.
    """
    _public_guard(match_id)
    cond = "t_ms >= {ft:Int64}" if from_t is not None else "seq >= {f:Int64}"
    rows = ch.query_rows(
        "SELECT seq, any(t_ms) AS t, any(period) AS period, "
        "groupArray((entity_id, entity_type, ifNull(team_id,''), round(x_m,2), round(y_m,2), "
        "ifNull(is_detected, false), round(ifNull(speed_mps, -1), 2))) AS ents "
        f"FROM positions FINAL WHERE session_id={{s:String}} AND match_id={{m:String}} AND {cond} "
        "GROUP BY seq ORDER BY seq LIMIT {l:Int32}",
        {"s": _id(session_id), "m": _id(match_id), "f": from_seq, "ft": from_t or 0, "l": limit})
    return {"frames": [{"seq": r["seq"], "t": r["t"], "period": r["period"], "ents": r["ents"]} for r in rows]}


@app.websocket("/api/ws/sessions/{session_id}")
async def ws_frames(ws: WebSocket, session_id: str, match_id: str, from_seq: int = 0):
    """Push processed frames as they land in ClickHouse (poll-based, bounded batches)."""
    await ws.accept()
    _id(session_id)
    _id(match_id)
    nxt = from_seq
    try:
        while True:
            chunk = await asyncio.to_thread(frames, session_id, match_id, nxt, 250)
            if chunk["frames"]:
                nxt = chunk["frames"][-1]["seq"] + 1
                await ws.send_text(json.dumps(chunk, default=str))
            else:
                await asyncio.sleep(0.4)
    except WebSocketDisconnect:
        return


# ------------------------------------------------------------------ metrics
@app.get("/api/sessions/{session_id}/heatmap")
def heatmap(session_id: str, match_id: str, entity_id: str | None = None, team_id: str | None = None,
            period: int | None = None, t_from: int | None = None, t_to: int | None = None,
            mode: str = Query("replay_time", pattern="^(replay_time|post_match)$")):
    """Time-weighted dwell (ms) per cell. Time filters are window-aligned (60 s windows)."""
    meta = match_meta(_public_guard(match_id))
    cur = _cursor_t(_id(session_id), match_id, mode, t_to)
    conds = ["session_id={s:String}", "match_id={m:String}"]
    p = {"s": session_id, "m": match_id}
    if entity_id:
        conds.append("entity_id={e:String}")
        p["e"] = _id(entity_id)
    if team_id:
        conds.append("team_id={tm:String}")
        p["tm"] = _id(team_id)
    if period:
        conds.append("intDiv(window, 10000) = {p:Int32}")
        p["p"] = period
    rows = ch.query_rows(
        f"SELECT cell_x, cell_y, sum(dwell_ms) AS dwell_ms FROM dwell FINAL WHERE {' AND '.join(conds)} "
        f"GROUP BY cell_x, cell_y", p)
    win = ch.query_rows(
        f"SELECT sum(active_ms) AS active_ms, sum(no_cell_ms) AS no_cell_ms, sum(excluded_gap_ms) AS excluded_ms "
        f"FROM player_windows FINAL WHERE {' AND '.join(conds)}", p)
    from smip.features.context import sport_config

    cfg = sport_config(meta["sport"])
    total = sum(r["dwell_ms"] for r in rows)
    return {"grid": {"nx": cfg.grid_nx, "ny": cfg.grid_ny}, "dimensions": meta["dimensions"],
            "cells": rows, "total_dwell_ms": total, "reconciliation": win[0] if win else None,
            "coordinate_space": "attack-normalized (team attacks toward +x)", "cursor_t": cur, "mode": mode,
            "note": "window-aligned; includes provider-extrapolated positions (flagged in positions table)"}


@app.get("/api/sessions/{session_id}/players")
def players(session_id: str, match_id: str):
    meta = match_meta(_public_guard(match_id))
    names = {p["canonical_player_id"]: p for p in meta.get("players", [])}
    rows = ch.query_rows(
        "SELECT entity_id, any(team_id) AS team_id, sum(distance_m) AS distance_m, sum(distance_raw_m) AS distance_raw_m, "
        "sum(active_ms) AS active_ms, sum(detected_ms) AS detected_ms, sum(hi_distance_m) AS hi_distance_m, "
        "sum(sprint_count) AS sprints, max(max_speed_mps) AS max_speed_mps, sum(excluded_gap_ms) AS excluded_gap_ms, "
        "sum(in_poss_ms) AS in_poss_ms, sum(out_poss_ms) AS out_poss_ms, countIf(is_final) AS final_windows, "
        "count() AS windows FROM player_windows FINAL WHERE session_id={s:String} AND match_id={m:String} "
        "GROUP BY entity_id ORDER BY distance_m DESC", {"s": _id(session_id), "m": match_id})
    for r in rows:
        pm = names.get(r["entity_id"], {})
        r.update(name=pm.get("name"), jersey=pm.get("jersey"), position=pm.get("position"))
        am = r["active_ms"] / 60000 if r["active_ms"] else None
        r["distance_per_active_min_m"] = round(r["distance_m"] / am, 1) if am else None
        r["detected_share"] = round(r["detected_ms"] / r["active_ms"], 3) if r["active_ms"] else None
    return {"players": rows, "units": {"distance": "m", "time": "ms", "speed": "m/s"},
            "method": "computed (causal EMA smoothing); raw distance provided for sensitivity"}


@app.get("/api/sessions/{session_id}/team_metrics")
def team_metrics(session_id: str, match_id: str, step: int = Query(10, ge=1, le=250)):
    p = {"s": _id(session_id), "m": _public_guard(match_id), "st": step}
    windows = ch.query_rows(
        "SELECT team_id, window, window_start_ms, window_end_ms, is_final, n_frames, n_sufficient, "
        "mean_width_m, mean_depth_m, mean_hull_area_m2, mean_def_line_height_m, mean_centroid_x "
        "FROM team_windows FINAL WHERE session_id={s:String} AND match_id={m:String} ORDER BY team_id, window", p)
    series = ch.query_rows(
        "SELECT team_id, seq, t_ms, period, width_m, depth_m, hull_area_m2, def_line_height_m, sufficient, "
        "spacing_hull_m2, mean_pairwise_m, paint_count, corner_count, offense "
        "FROM team_frames FINAL WHERE session_id={s:String} AND match_id={m:String} AND seq % {st:Int32} = 0 "
        "ORDER BY team_id, seq", p)
    return {"windows": windows, "series": series,
            "labels": {"width_m": "deterministic geometry", "def_line_height_m": "heuristic (mean of 4 deepest outfield)"}}


@app.get("/api/pipeline/health")
def pipeline_health(session_id: str | None = None):
    sess = ch.query_rows(
        "SELECT session_id, match_id, status, frames_sent, last_seq, updated_at FROM replay_sessions FINAL "
        + ("WHERE session_id={s:String} " if session_id else "") + "ORDER BY updated_at DESC LIMIT 10",
        {"s": session_id} if session_id else None)
    out = []
    for s in sess:
        p = {"s": s["session_id"], "m": s["match_id"]}
        fr = ch.query_rows(
            "SELECT count() AS frames, max(seq) AS max_seq, "
            "quantileExact(0.5)(dateDiff('millisecond', produced_at, processed_at)) AS p50_ms, "
            "quantileExact(0.95)(dateDiff('millisecond', produced_at, processed_at)) AS p95_ms, "
            "max(processed_at) AS last_processed FROM frames WHERE session_id={s:String} AND match_id={m:String}", p)
        q = ch.query_rows("SELECT reason, count() AS n FROM quarantine WHERE session_id={s:String} "
                          "GROUP BY reason", p)
        st = cursor(s["session_id"], s["match_id"])
        out.append({**s, "processed": fr[0] if fr else None, "quarantine": q,
                    "engine": {k: v for k, v in st.items() if k.startswith(("c_", "buffer", "cursor", "hwm", "released"))}})
    ledger = ch.query_rows("SELECT query_name, count() AS batches, max(committed_at) AS last_commit, "
                           "avg(duration_ms) AS avg_batch_ms, sum(rows) AS rows FROM sink_ledger GROUP BY query_name")
    return {"sessions": out, "sinks": ledger, "generated_at": time.time(),
            "semantics": "Iceberg: tag-checked appends per batch; ClickHouse: at-least-once + ReplacingMergeTree FINAL"}


# ------------------------------------------------------------ ML + lineage
@app.get("/api/sessions/{session_id}/similar")
def similar_moments(session_id: str, match_id: str, t_ms: int, k: int = Query(5, ge=1, le=10),
                    mode: str = Query("replay_time", pattern="^(replay_time|post_match)$")):
    from smip.ml.moments import get_index, similar

    _public_guard(match_id)
    cur = _cursor_t(_id(session_id), _id(match_id), "replay_time", None)
    t_max = cur if mode == "replay_time" else None
    idx = get_index(session_id, match_id, t_max)
    if idx is None or len(idx) < 10:
        return {"neighbours": [], "index_size": 0 if idx is None else len(idx), "cursor_t": cur}
    out = similar(idx, min(t_ms, cur if cur is not None else t_ms), k)
    return {**out, "cursor_t": cur, "mode": mode}


@app.get("/api/sessions/{session_id}/changes")
def shape_changes(session_id: str, match_id: str,
                  mode: str = Query("replay_time", pattern="^(replay_time|post_match)$")):
    from smip.ml.changes import get_changes

    _public_guard(match_id)
    cur = _cursor_t(_id(session_id), _id(match_id), "replay_time", None)
    res = get_changes(session_id, match_id, cur if mode == "replay_time" else None)
    return {**res, "cursor_t": cur, "mode": mode}


@app.get("/api/sessions/{session_id}/lineage")
def session_lineage(session_id: str, match_id: str):
    from smip.lakehouse import lineage

    _public_guard(match_id)
    try:
        res = lineage(_id(session_id), _id(match_id))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"lakehouse unavailable: {type(exc).__name__}") from None
    res["kafka"] = {"topic": "smip.tracking.v1", "key": f"{session_id}|{match_id}"}
    ledger = ch.query_rows("SELECT query_name, count() AS batches, sum(rows) AS rows, avg(duration_ms) AS avg_ms "
                           "FROM sink_ledger FINAL GROUP BY query_name")
    res["sink_ledger"] = ledger
    return res


class Ask(BaseModel):
    question: str = Field(max_length=500)
    session_id: str
    match_id: str
    mode: str = Field("replay_time", pattern="^(replay_time|post_match)$")
    as_of_ms: int | None = Field(None, ge=0)


@app.post("/api/analyst/ask")
def analyst_ask(req: Ask):
    from smip.analyst.router import ask

    _public_guard(req.match_id)
    return ask(req.question, _id(req.session_id), _id(req.match_id), req.mode, req.as_of_ms)


@app.get("/api/demo")
def demo_info():
    """Demo sessions and their last verification report (parity, lineage, ML/analyst evals)."""
    from smip.config import get_settings
    from smip.demo import visible_sessions

    d = get_settings().data_dir / "demo"

    def load(name):
        f = d / name
        return json.loads(f.read_text()) if f.exists() else None

    seed = load("seed_report.json") or {"sessions": {}}
    out = []
    for s in visible_sessions():
        rep = seed["sessions"].get(s.key, {})
        out.append({"key": s.key, "session_id": s.session_id, "match_id": s.match_id, "speed": s.speed,
                    "public": s.public, "faults": asdict(s.faults), "ok": rep.get("ok"),
                    "parity": rep.get("parity"), "engine_counters": rep.get("engine_counters"),
                    "ml_eval": load(f"ml_eval_{s.session_id}.json")})
    return {"public_demo": get_settings().public_demo, "sessions": out, "analyst_eval": load("analyst_eval.json"),
            "seed_generated_at": seed.get("generated_at")}


# -------------------------------------------------------------------- static UI
_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = _dist / path
        return FileResponse(f if path and f.is_file() else _dist / "index.html")
