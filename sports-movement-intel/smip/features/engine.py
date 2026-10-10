"""Incremental, causal per-match feature engine shared by Spark streaming and batch backfill.

One engine instance owns the state for one (replay_session_id, match_id). Its state is a bounded
JSON-serializable dict so Spark's ``applyInPandasWithState`` can persist it between micro-batches.

Processing contract
-------------------
1. Frames enter a reorder buffer keyed by canonical ``sequence``. A frame is released (processed in
   sequence order) once ``hwm - sequence >= reorder_window_frames``, or on end-of-stream/flush.
2. Duplicate sequences (transport or injected) are dropped and counted. A frame whose sequence is
   already released is "late beyond reorder buffer": it is emitted as a ``late`` record (kept for
   audit in the quarantine table) and never mutates finalized metrics.
3. Corrections (``injected_correction`` flag) replace a buffered frame; after release they are
   recorded as late corrections and not applied.
4. Kinematics use physical meters and ``physical_time_ms``. A segment breaks on period change, on a
   gap above ``max_gap_ms`` or an implausible jump; no distance is accumulated across breaks.
5. Speeds use a causal EMA of positions (no future frames). Raw (unsmoothed) distance is emitted too
   for sensitivity analysis.
6. Time-weighted dwell: each valid interval [t_prev, t] is attributed to the previous position's
   cell and to the window containing t_prev. Therefore sum(dwell_ms) == active_ms exactly.
7. Windows are fixed ``window_ms`` buckets of physical game time (never replay wall time). A window
   finalizes when a released frame reaches its end or at end-of-stream. Partial (online) window
   rows are emitted with ``is_final = False`` and superseded by the final row.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from smip.features.context import MatchContext, SportConfig

ENGINE_VERSION = "1.0.0"


def hull_area(points: np.ndarray) -> float | None:
    """Convex hull area (monotone chain). None for fewer than 3 points."""
    if len(points) < 3:
        return None
    pts = sorted(map(tuple, points))

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return 0.0
    area = 0.0
    for i in range(len(hull)):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % len(hull)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def _f(v):
    """JSON-safe float: NaN/inf -> None."""
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) or math.isinf(v) else round(v, 4)


def compact_frame(msg: dict) -> dict:
    """Keep only fields the engine needs (bounded state size)."""
    ents = []
    for e in ([msg["ball"]] if msg.get("ball") else []) + (msg.get("players") or []):
        ents.append([
            e.get("canonical_player_id"), e.get("entity_type"), e.get("team_id"),
            e.get("x_m"), e.get("y_m"), e.get("z_m"), e.get("x_att"), e.get("y_att"),
            e.get("is_detected"), e.get("position_source"),
        ])
    return {
        "seq": msg["sequence"], "t": msg.get("physical_time_ms"), "mel": msg.get("match_elapsed_ms"),
        "period": msg.get("period"), "sfid": msg.get("source_frame_id"), "clock": msg.get("source_clock"),
        "poss": msg.get("possession_team_id"), "flags": msg.get("quality_flags") or [],
        "attempt": msg.get("attempt", 0), "ret": msg.get("replay_event_time"), "pat": msg.get("produced_at"),
        "ents": ents,
    }


class MatchEngine:
    def __init__(self, session_id: str, ctx: MatchContext, cfg: SportConfig, state: dict | None = None,
                 frame_hooks: list | None = None):
        self.session_id = session_id
        self.ctx = ctx
        self.cfg = cfg
        self.frame_hooks = frame_hooks or []
        s = state or {}
        self.hwm: int = s.get("hwm", -1)
        self.released_upto: int = s.get("released_upto", -1)
        self.released: list[list[int]] = s.get("released", [])      # merged [a, b] intervals
        self.buffer: dict[int, dict] = {int(k): v for k, v in s.get("buffer", {}).items()}
        self.last: dict[str, list] = s.get("last", {})
        self.pwin: dict[str, dict] = s.get("pwin", {})
        self.twin: dict[str, dict] = s.get("twin", {})
        self.dwell: dict[str, dict] = s.get("dwell", {})
        self.counters: dict[str, int] = defaultdict(int, s.get("counters", {}))
        self.cursor_t: int | None = s.get("cursor_t")
        self.cursor_mel: int | None = s.get("cursor_mel")
        self.ended: bool = s.get("ended", False)
        self._out: dict[str, list] = defaultdict(list)
        self._touched_windows: set[str] = set()

    # ---------------------------------------------------------------- state
    def to_state(self) -> dict:
        return {
            "v": ENGINE_VERSION, "hwm": self.hwm, "released_upto": self.released_upto,
            "released": self.released, "buffer": {str(k): v for k, v in self.buffer.items()},
            "last": self.last, "pwin": self.pwin, "twin": self.twin, "dwell": self.dwell,
            "counters": dict(self.counters), "cursor_t": self.cursor_t, "cursor_mel": self.cursor_mel,
            "ended": self.ended,
        }

    def _is_released(self, seq: int) -> bool:
        return any(a <= seq <= b for a, b in self.released)

    def _mark_released(self, seq: int) -> None:
        iv = self.released
        if iv and iv[-1][1] + 1 == seq:
            iv[-1][1] = seq
        elif iv and iv[-1][1] >= seq:
            # out-of-order release cannot happen (we release in order); keep for safety
            for rng in iv:
                if rng[0] <= seq <= rng[1]:
                    return
            iv.append([seq, seq])
            iv.sort()
        else:
            iv.append([seq, seq])
        if len(iv) > 2000:  # bound state: merge oldest intervals conservatively
            self.released = [[iv[0][0], iv[-1000][1]]] + iv[-999:]

    # --------------------------------------------------------------- ingest
    def ingest(self, messages: list[dict]) -> dict[str, list]:
        """Ingest raw frame messages (any order). Returns emitted records by kind."""
        end_seen = False
        for msg in sorted(messages, key=lambda m: (m.get("sequence", 0), m.get("attempt", 0))):
            if msg.get("end_of_stream"):
                end_seen = True
                continue
            seq = int(msg["sequence"])
            if self.ended:  # session already finalized: never reopen finalized windows
                self.counters["after_end"] += 1
                self._emit("late", {"seq": seq, "reason": "after_end_of_stream", "t": msg.get("physical_time_ms"),
                                    "attempt": msg.get("attempt", 0)})
                continue
            flags = msg.get("quality_flags") or []
            is_correction = "injected_correction" in flags
            if seq <= self.released_upto or self._is_released(seq):
                kind = "late_correction" if is_correction else (
                    "duplicate" if self._is_released(seq) else "late_beyond_reorder_buffer")
                self.counters[kind] += 1
                if kind != "duplicate":
                    self._emit("late", {"seq": seq, "reason": kind, "t": msg.get("physical_time_ms"),
                                        "attempt": msg.get("attempt", 0)})
                continue
            if seq in self.buffer:
                if is_correction:
                    self.buffer[seq] = compact_frame(msg)
                    self.counters["corrections_applied"] += 1
                else:
                    self.counters["duplicate"] += 1
                continue
            if seq < self.hwm:
                self.counters["reordered"] += 1
            self.buffer[seq] = compact_frame(msg)
            self.hwm = max(self.hwm, seq)
        self._release(flush=False)
        if end_seen and not self.ended:
            self._finalize_all()
        elif self.ended:
            pass
        else:
            self._emit_partials()
        self._emit_stats()
        return self._drain()

    def finalize(self) -> dict[str, list]:
        """End of replay (or inactivity timeout): release everything, finalize all windows."""
        self._finalize_all()
        self._emit_stats()
        return self._drain()

    def _finalize_all(self) -> None:
        self._release(flush=True)
        for key in list(self.pwin):
            self._finalize_player_window(key)
        for key in list(self.twin):
            self._finalize_team_window(key)
        self.last = {}
        self.ended = True

    # --------------------------------------------------------------- release
    def _release(self, flush: bool) -> None:
        depth = self.cfg.reorder_window_frames
        for seq in sorted(self.buffer):
            if not flush and self.hwm - seq < depth:
                break
            fr = self.buffer.pop(seq)
            if seq > self.released_upto + 1 and self.released_upto >= 0:
                self.counters["sequence_gaps"] += 1
                self.counters["missing_frames"] += seq - self.released_upto - 1
            self._process_frame(fr)
            self._mark_released(seq)
            self.released_upto = max(self.released_upto, seq)

    def _window(self, t: int, period: int) -> int:
        """Period-relative window id: period * 10000 + index of window_ms bucket since period start."""
        off = dict(self.ctx.period_offsets).get(period, 0)
        return int(period) * 10000 + int(max(t - off, 0) // self.cfg.window_ms)

    def _window_bounds(self, w: int) -> tuple[int, int]:
        period, idx = divmod(w, 10000)
        off = dict(self.ctx.period_offsets).get(period, 0)
        start = off + idx * self.cfg.window_ms
        return start, start + self.cfg.window_ms

    def _cell(self, x_att, y_att) -> tuple[int, int] | None:
        if x_att is None or y_att is None:
            return None
        L, W = self.ctx.length_m, self.ctx.width_m
        cx = int((x_att + L / 2) / L * self.cfg.grid_nx)
        cy = int((y_att + W / 2) / W * self.cfg.grid_ny)
        return (min(max(cx, 0), self.cfg.grid_nx - 1), min(max(cy, 0), self.cfg.grid_ny - 1))

    def _process_frame(self, fr: dict) -> None:
        t, period, poss = fr["t"], fr["period"], fr["poss"]
        self.counters["frames_released"] += 1
        n_players = sum(1 for e in fr["ents"] if e[1] == "player")
        n_det = sum(1 for e in fr["ents"] if e[1] == "player" and e[8])
        self._emit("frame", {
            "seq": fr["seq"], "source_frame_id": fr["sfid"], "t": t, "mel": fr["mel"], "period": period,
            "clock": fr["clock"], "poss_team": poss, "n_players": n_players, "n_detected": n_det,
            "has_ball": any(e[1] == "ball" for e in fr["ents"]), "flags": ",".join(fr["flags"]),
            "attempt": fr["attempt"], "replay_event_time": fr["ret"], "produced_at": fr["pat"],
        })
        if t is None:
            return
        self.cursor_t = t if self.cursor_t is None else max(self.cursor_t, t)
        if fr["mel"] is not None:
            self.cursor_mel = fr["mel"] if self.cursor_mel is None else max(self.cursor_mel, fr["mel"])
        cfg = self.cfg
        a = cfg.ema_alpha
        # Team windows accumulate per frame time, so they close as soon as a frame enters a later window.
        # Player windows accumulate intervals by their start time, so they close only when no future
        # interval can start inside them (released time beyond window end + max_gap_ms, or a new period).
        w_now = self._window(t, period)
        for key in [k for k, v in self.twin.items() if v["w"] < w_now]:
            self._finalize_team_window(key)
        for key in [k for k, v in self.pwin.items()
                    if v["w"] // 10000 != period or self._window_bounds(v["w"])[1] + cfg.max_gap_ms < t]:
            self._finalize_player_window(key)

        for eid, etype, team, x, y, z, xa, ya, det, psrc in fr["ents"]:
            if eid is None or x is None or y is None:
                continue
            cell = self._cell(xa, ya)
            prev = self.last.get(eid)
            speed = accel = d_raw = d_s = None
            seg_start, gap_ms, implausible = True, None, False
            sx, sy = x, y
            below_ms = 10**9 if prev is None else prev[11]
            in_sprint = False if prev is None else prev[10]
            if prev is not None:
                pt, pper, px, py, psx, psy, pspeed, pcell, pteam, pdet = prev[:10]
                dt_ms = t - pt
                gap_ms = dt_ms
                if pper == period and 0 < dt_ms <= cfg.max_gap_ms:
                    dt = dt_ms / 1000.0
                    d_raw = math.hypot(x - px, y - py)
                    vmax = cfg.max_speed_ball if etype == "ball" else cfg.max_speed_player
                    if d_raw / dt > vmax:
                        implausible = True
                        self.counters["implausible_jumps"] += 1
                        d_raw = None
                    else:
                        seg_start = False
                        sx, sy = a * x + (1 - a) * psx, a * y + (1 - a) * psy
                        d_s = math.hypot(sx - psx, sy - psy)
                        speed = d_s / dt
                        accel = None if pspeed is None else (speed - pspeed) / dt
                        if etype == "player":
                            self._accumulate_player(eid, pteam or team, pt, period, dt_ms, d_s, d_raw, speed, accel,
                                                    pcell, bool(pdet) and bool(det), poss, in_sprint, below_ms)
                            if speed >= cfg.sprint_speed_mps:
                                in_sprint, below_ms = True, 0
                            else:
                                if in_sprint:
                                    below_ms = 0
                                in_sprint = False
                                below_ms += dt_ms
                elif pper == period and dt_ms > cfg.max_gap_ms and etype == "player":
                    self._excluded_gap(eid, pteam or team, t, period, dt_ms)
                    self.counters["segment_breaks_gap"] += 1
            self.last[eid] = [t, period, x, y, sx, sy, speed, cell, team, det, in_sprint, below_ms]
            self._emit("obs", {
                "seq": fr["seq"], "t": t, "mel": fr["mel"], "period": period, "entity_id": eid,
                "entity_type": etype, "team_id": team, "x_m": _f(x), "y_m": _f(y), "z_m": _f(z),
                "x_att": _f(xa), "y_att": _f(ya), "is_detected": det, "position_source": psrc,
                "speed_mps": _f(speed), "accel_mps2": _f(accel), "dist_raw_m": _f(d_raw), "dist_m": _f(d_s),
                "segment_start": seg_start, "gap_ms": gap_ms, "implausible": implausible,
                "cell_x": None if cell is None else cell[0], "cell_y": None if cell is None else cell[1],
            })
        self._team_frame(fr)

    # ------------------------------------------------------------ accumulate
    def _pw(self, eid: str, team: str | None, w: int) -> dict:
        key = f"{eid}|{w}"
        acc = self.pwin.get(key)
        if acc is None:
            acc = self.pwin[key] = {
                "e": eid, "team": team, "w": w, "dist": 0.0, "dist_raw": 0.0, "active": 0, "det_ms": 0,
                "hi_ms": 0, "sprint_ms": 0, "hi_dist": 0.0, "sprints": 0, "acc_n": 0, "dec_n": 0,
                "vmax": 0.0, "in_poss": 0, "out_poss": 0, "poss_unknown": 0, "n": 0, "excl_gap": 0,
                "last_seq": -1,
            }
        self._touched_windows.add("p:" + key)
        return acc

    def _accumulate_player(self, eid, team, t_start, period, dt_ms, d_s, d_raw, speed, accel, cell, both_det, poss,
                           in_sprint, below_ms) -> None:
        cfg = self.cfg
        acc = self._pw(eid, team, self._window(t_start, period))
        acc["dist"] += d_s
        acc["dist_raw"] += d_raw
        acc["active"] += dt_ms
        acc["n"] += 1
        acc["last_seq"] = self.released_upto + 1
        if both_det:
            acc["det_ms"] += dt_ms
        if speed >= cfg.hi_speed_mps:
            acc["hi_ms"] += dt_ms
            acc["hi_dist"] += d_s
        if speed >= cfg.sprint_speed_mps:
            acc["sprint_ms"] += dt_ms
            if not in_sprint and below_ms >= 1000:
                acc["sprints"] += 1
        if accel is not None:
            if accel >= cfg.accel_threshold_mps2:
                acc["acc_n"] += 1
            elif accel <= -cfg.accel_threshold_mps2:
                acc["dec_n"] += 1
        acc["vmax"] = max(acc["vmax"], speed)
        if poss is None:
            acc["poss_unknown"] += dt_ms
        elif poss == team:
            acc["in_poss"] += dt_ms
        else:
            acc["out_poss"] += dt_ms
        if cell is not None:
            dkey = f"{eid}|{acc['w']}"
            d = self.dwell.setdefault(dkey, {})
            ck = f"{cell[0]},{cell[1]}"
            d[ck] = d.get(ck, 0) + dt_ms
        else:
            acc.setdefault("no_cell_ms", 0)
            acc["no_cell_ms"] += dt_ms

    def _excluded_gap(self, eid, team, t_end, period, gap_ms) -> None:
        """Gaps are recorded in the window where they end: the window where they began may be final."""
        acc = self._pw(eid, team, self._window(t_end, period))
        acc["excl_gap"] += gap_ms

    def _team_frame(self, fr: dict) -> None:
        by_team: dict[str, list] = defaultdict(list)
        for eid, etype, team, _x, _y, _z, xa, ya, det, _psrc in fr["ents"]:
            if etype == "player" and team is not None and xa is not None and ya is not None:
                by_team[team].append((eid, xa, ya, bool(det)))
        L = self.ctx.length_m
        for team in self.ctx.team_ids:
            pl = by_team.get(team, [])
            outfield = [p for p in pl if p[0] not in self.ctx.goalkeepers]
            n_det = sum(1 for p in outfield if p[3])
            ok = len(outfield) >= self.cfg.min_outfield_for_shape
            rec = {"seq": fr["seq"], "t": fr["t"], "mel": fr["mel"], "period": fr["period"], "team_id": team,
                   "n_outfield": len(outfield), "n_detected": n_det, "sufficient": ok,
                   "in_possession": None if fr["poss"] is None else fr["poss"] == team}
            if ok:
                pts = np.array([[p[1], p[2]] for p in outfield])
                xs = np.sort(pts[:, 0])
                rec.update(
                    centroid_x=_f(pts[:, 0].mean()), centroid_y=_f(pts[:, 1].mean()),
                    width_m=_f(pts[:, 1].max() - pts[:, 1].min()), depth_m=_f(xs[-1] - xs[0]),
                    hull_area_m2=_f(hull_area(pts)),
                    def_line_height_m=_f(xs[:4].mean() + L / 2) if self.ctx.sport == "soccer" else None,
                )
            for hook in self.frame_hooks:
                rec.update(hook(fr, team, pl, self.ctx) or {})
            self._emit("team_frame", rec)
            if fr["t"] is not None:
                self._accumulate_team(team, fr["t"], fr["period"], rec)

    def _accumulate_team(self, team: str, t: int, period: int, rec: dict) -> None:
        w = self._window(t, period)
        key = f"{team}|{w}"
        acc = self.twin.get(key)
        if acc is None:
            acc = self.twin[key] = {"team": team, "w": w, "n": 0, "n_ok": 0, "sums": {}, "in_poss_n": 0}
        self._touched_windows.add("t:" + key)
        acc["n"] += 1
        if rec.get("in_possession"):
            acc["in_poss_n"] += 1
        if rec["sufficient"]:
            acc["n_ok"] += 1
            for k in ("centroid_x", "width_m", "depth_m", "hull_area_m2", "def_line_height_m"):
                if rec.get(k) is not None:
                    s = acc["sums"].setdefault(k, [0.0, 0])
                    s[0] += rec[k]
                    s[1] += 1

    # ---------------------------------------------------------------- emit
    def _player_window_row(self, acc: dict, final: bool) -> dict:
        w = acc["w"]
        ws, we = self._window_bounds(w)
        return {
            "entity_id": acc["e"], "team_id": acc["team"], "window": w, "window_start_ms": ws,
            "window_end_ms": we, "is_final": final,
            "distance_m": _f(acc["dist"]), "distance_raw_m": _f(acc["dist_raw"]), "active_ms": acc["active"],
            "detected_ms": acc["det_ms"], "hi_ms": acc["hi_ms"], "sprint_ms": acc["sprint_ms"],
            "hi_distance_m": _f(acc["hi_dist"]), "sprint_count": acc["sprints"], "accel_count": acc["acc_n"],
            "decel_count": acc["dec_n"], "max_speed_mps": _f(acc["vmax"]), "in_poss_ms": acc["in_poss"],
            "out_poss_ms": acc["out_poss"], "poss_unknown_ms": acc["poss_unknown"], "n_intervals": acc["n"],
            "excluded_gap_ms": acc["excl_gap"], "no_cell_ms": acc.get("no_cell_ms", 0),
            "version": self.released_upto * 2 + (1 if final else 0),
        }

    def _dwell_rows(self, eid: str, team, w: int, final: bool) -> None:
        d = self.dwell.get(f"{eid}|{w}", {})
        for ck, ms in d.items():
            cx, cy = map(int, ck.split(","))
            self._emit("dwell", {"entity_id": eid, "team_id": team, "window": w, "cell_x": cx, "cell_y": cy,
                                 "dwell_ms": ms, "is_final": final,
                                 "version": self.released_upto * 2 + (1 if final else 0)})

    def _team_window_row(self, acc: dict, final: bool) -> dict:
        w = acc["w"]
        ws, we = self._window_bounds(w)
        row = {"team_id": acc["team"], "window": w, "window_start_ms": ws,
               "window_end_ms": we, "is_final": final, "n_frames": acc["n"],
               "n_sufficient": acc["n_ok"], "in_possession_frames": acc["in_poss_n"],
               "version": self.released_upto * 2 + (1 if final else 0)}
        for k in ("centroid_x", "width_m", "depth_m", "hull_area_m2", "def_line_height_m"):
            s = acc["sums"].get(k)
            row[f"mean_{k}"] = _f(s[0] / s[1]) if s and s[1] else None
        return row

    def _finalize_player_window(self, key: str) -> None:
        acc = self.pwin.pop(key)
        self._emit("player_window", self._player_window_row(acc, True))
        self._dwell_rows(acc["e"], acc["team"], acc["w"], True)
        self.dwell.pop(f"{acc['e']}|{acc['w']}", None)
        self._touched_windows.discard("p:" + key)

    def _finalize_team_window(self, key: str) -> None:
        acc = self.twin.pop(key)
        self._emit("team_window", self._team_window_row(acc, True))
        self._touched_windows.discard("t:" + key)

    def _emit_partials(self) -> None:
        for tk in sorted(self._touched_windows):
            kind, key = tk.split(":", 1)
            if kind == "p" and key in self.pwin:
                acc = self.pwin[key]
                self._emit("player_window", self._player_window_row(acc, False))
                self._dwell_rows(acc["e"], acc["team"], acc["w"], False)
            elif kind == "t" and key in self.twin:
                self._emit("team_window", self._team_window_row(self.twin[key], False))
        self._touched_windows.clear()

    def _emit_stats(self) -> None:
        self._emit("stats", {
            "hwm": self.hwm, "released_upto": self.released_upto, "buffer_size": len(self.buffer),
            "cursor_t": self.cursor_t, "cursor_mel": self.cursor_mel, "ended": self.ended,
            "state_entities": len(self.last), "open_player_windows": len(self.pwin),
            **{f"c_{k}": v for k, v in self.counters.items()},
        })

    def _emit(self, kind: str, rec: dict) -> None:
        self._out[kind].append(rec)

    def _drain(self) -> dict[str, list]:
        out, self._out = self._out, defaultdict(list)
        return out
