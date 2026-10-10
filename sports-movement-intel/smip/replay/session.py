"""Deterministic historical replay sessions -> Kafka.

Clocks (see docs/CLOCKS.md):
* source/game time: ``period``, ``source_clock``, ``match_elapsed_ms``, ``source_frame_id`` from the
  normalized match; never modified by replay.
* replay event time: ``session_base + physical_time_ms``. It is independent of playback speed, pauses
  and wall-clock scheduling, so game-time windows are identical at 0.5x, 1x, 20x or unthrottled.
* processing time: ``produced_at`` (wall clock at produce), Kafka append time and sink
  ``processed_at``; used only for freshness/latency.

Scheduling: frame i is due at ``anchor_wall + (t_i - anchor_t) / speed`` (re-anchored on speed
change/resume). Basketball dead-ball gaps above ``max_sched_gap_ms`` are compressed for *scheduling
only* and the frame is flagged ``dead_ball_gap_compressed``; its event time is unchanged.
"""

from __future__ import annotations

import copy
import json
import logging
import random
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from smip.config import get_settings
from smip.replay.frames import iter_frames, load_meta, roster

log = logging.getLogger(__name__)
TOPIC = "smip.tracking.v1"
MAX_FAULT_RATE = 0.2


@dataclass
class FaultConfig:
    duplicate_rate: float = 0.0
    delay_rate: float = 0.0
    delay_frames: int = 5          # delivered this many frames later (inside/outside reorder buffer)
    drop_rate: float = 0.0
    out_of_order_rate: float = 0.0
    correction_rate: float = 0.0
    correction_lag_frames: int = 3
    malformed_rate: float = 0.0    # emits an invalid JSON record (quarantine path)

    def validate(self) -> FaultConfig:
        for k, v in asdict(self).items():
            if k.endswith("_rate") and not 0.0 <= v <= MAX_FAULT_RATE:
                raise ValueError(f"{k}={v} outside [0, {MAX_FAULT_RATE}]")
        return self


@dataclass
class SessionSpec:
    match_id: str
    speed: float = 1.0                 # 0 => unthrottled benchmark
    session_id: str | None = None
    seed: int = 7
    faults: FaultConfig = field(default_factory=FaultConfig)
    start_seq: int = 0
    end_seq: int | None = None
    resume: bool = False               # retry an existing session from its checkpoint
    max_sched_gap_ms: int = 2000


def new_session_id(match_id: str) -> str:
    return f"rs-{match_id.replace(':', '-')}-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ReplaySession:
    def __init__(self, spec: SessionSpec, producer=None):
        spec.faults.validate()
        self.spec = spec
        self.meta = load_meta(spec.match_id)
        self.session_id = spec.session_id or new_session_id(spec.match_id)
        self.key = f"{self.session_id}|{spec.match_id}".encode()
        self.state_path = get_settings().state_dir / "replay" / f"{self.session_id}.json"
        self.checkpoint = self._load_checkpoint()
        if spec.resume and not self.checkpoint:
            raise ValueError(f"cannot resume unknown session {self.session_id}")
        if not spec.resume and self.checkpoint:
            raise ValueError(f"session {self.session_id} exists; use resume=True or a new session id")
        self.session_base = (datetime.fromisoformat(self.checkpoint["session_base"]) if self.checkpoint
                             else datetime.now(timezone.utc).replace(microsecond=0))
        self.attempt = (self.checkpoint.get("attempt", 0) + 1) if self.checkpoint else 0
        self.producer = producer or make_producer()
        self.rng = random.Random(spec.seed)
        self._speed = spec.speed
        self._paused = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.frames_sent = 0
        self.last_seq = -1
        self.status = "created"
        self.started_wall = time.time()
        self.thread: threading.Thread | None = None

    # ------------------------------------------------------------ control
    def pause(self):
        self._paused.set()
        self.status = "paused"
        self._register()

    def resume_playback(self):
        self._paused.clear()
        self.status = "running"
        self._register()

    def set_speed(self, speed: float):
        with self._lock:
            self._speed = speed
        self._register()

    def stop(self):
        self._stop.set()

    def start_thread(self):
        self.thread = threading.Thread(target=self.run, name=self.session_id, daemon=True)
        self.thread.start()
        return self

    # ---------------------------------------------------------- checkpoint
    def _load_checkpoint(self) -> dict | None:
        return json.loads(self.state_path.read_text()) if self.state_path.exists() else None

    def _save_checkpoint(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({
            "session_id": self.session_id, "match_id": self.spec.match_id,
            "session_base": self.session_base.isoformat(), "last_seq_flushed": self.last_seq,
            "attempt": self.attempt, "speed": self._speed, "seed": self.spec.seed,
            "faults": asdict(self.spec.faults), "status": self.status,
        }))

    # ------------------------------------------------------------- produce
    def _envelope(self, fr: dict, flags: list[str] | None = None) -> dict:
        msg = dict(fr)
        msg["replay_session_id"] = self.session_id
        msg["replay_event_time"] = _iso(self.session_base + timedelta(milliseconds=fr["physical_time_ms"] or 0))
        msg["produced_at"] = _iso(datetime.now(timezone.utc))
        msg["attempt"] = self.attempt
        if flags:
            msg["quality_flags"] = list(dict.fromkeys((msg.get("quality_flags") or []) + flags))
        return msg

    def _send(self, msg: dict | bytes):
        payload = msg if isinstance(msg, bytes) else json.dumps(msg, separators=(",", ":")).encode()
        while True:
            try:
                self.producer.produce(TOPIC, key=self.key, value=payload)
                break
            except BufferError:
                self.producer.poll(0.05)
        self.producer.poll(0)
        self.frames_sent += 1

    def run(self):
        spec, f = self.spec, self.spec.faults
        start = spec.start_seq
        if spec.resume and self.checkpoint:
            # retry: re-send a small overlap; the engine drops already-seen sequences
            start = max(0, self.checkpoint.get("last_seq_flushed", -1) - 50)
        self.status = "running"
        self._register()
        log.info("session %s match %s speed %s from seq %s attempt %s", self.session_id, spec.match_id,
                 self._speed, start, self.attempt)
        delayed: list[tuple[int, dict]] = []    # (release_after_index, msg)
        anchor_wall, anchor_t, last_t, sched_t = time.time(), None, None, 0.0
        speed_seen = self._speed
        i = 0
        last_ckpt = time.time()
        try:
            for fr in iter_frames(spec.match_id, start_seq=start, end_seq=spec.end_seq):
                if self._stop.is_set():
                    self.status = "stopped"
                    break
                while self._paused.is_set() and not self._stop.is_set():
                    time.sleep(0.05)
                    anchor_wall, anchor_t = time.time(), sched_t
                t = fr["physical_time_ms"] or 0
                flags: list[str] = []
                if last_t is not None:
                    gap = t - last_t
                    if gap > spec.max_sched_gap_ms and self.meta["sport"] == "basketball":
                        flags.append("dead_ball_gap_compressed")
                        gap = spec.max_sched_gap_ms
                    sched_t += max(gap, 0)
                last_t = t
                with self._lock:
                    speed = self._speed
                if speed != speed_seen:
                    anchor_wall, anchor_t, speed_seen = time.time(), sched_t, speed
                if anchor_t is None:
                    anchor_t = sched_t
                if speed > 0:
                    due = anchor_wall + (sched_t - anchor_t) / 1000.0 / speed
                    wait = due - time.time()
                    if wait > 0:
                        time.sleep(wait)
                # ---- faults (seeded, bounded)
                r = self.rng.random
                if f.drop_rate and r() < f.drop_rate:
                    i += 1
                    continue
                msg = self._envelope(fr, flags)
                if f.malformed_rate and r() < f.malformed_rate:
                    self._send(b'{"schema_version":"1.0.0","record_type":"tracking_frame","sequence":')
                if f.correction_rate and r() < f.correction_rate:
                    bad = copy.deepcopy(msg)
                    for p in bad["players"]:
                        if p.get("x_m") is not None:
                            p["x_m"] += 0.5
                    delayed.append((i + f.correction_lag_frames, self._envelope(fr, flags + ["injected_correction"])))
                    msg = bad
                if f.delay_rate and r() < f.delay_rate:
                    delayed.append((i + f.delay_frames, self._envelope(fr, flags + ["injected_delay"])))
                elif f.out_of_order_rate and r() < f.out_of_order_rate:
                    delayed.append((i + 1, self._envelope(fr, flags + ["injected_out_of_order"])))
                else:
                    self._send(msg)
                    if f.duplicate_rate and r() < f.duplicate_rate:
                        self._send(self._envelope(fr, flags + ["injected_duplicate"]))
                due_now = [d for d in delayed if d[0] <= i]
                delayed = [d for d in delayed if d[0] > i]
                for _, dm in due_now:
                    self._send(dm)
                self.last_seq = fr["sequence"]
                i += 1
                if time.time() - last_ckpt > 2.0:
                    self.producer.flush(10)
                    self._save_checkpoint()
                    self._register()
                    last_ckpt = time.time()
            for _, dm in delayed:
                self._send(dm)
            if self.status != "stopped":
                self._send({
                    "schema_version": "1.0.0", "record_type": "tracking_frame", "source": self.meta["source"],
                    "source_revision": self.meta["source_revision"], "sport": self.meta["sport"],
                    "match_id": spec.match_id, "record_id": f"{spec.match_id}|end_of_stream",
                    "replay_session_id": self.session_id, "sequence": self.last_seq + 1,
                    "physical_time_ms": last_t, "replay_event_time": _iso(self.session_base + timedelta(
                        milliseconds=last_t or 0)), "produced_at": _iso(datetime.now(timezone.utc)),
                    "attempt": self.attempt, "end_of_stream": True, "quality_flags": [], "players": [],
                    "roster": roster(spec.match_id),
                })
                self.status = "completed"
        except Exception as exc:
            self.status = "failed"
            log.exception("session %s failed: %s", self.session_id, exc)
            raise
        finally:
            self.producer.flush(30)
            self._save_checkpoint()
            self._register()
            log.info("session %s %s frames_sent=%d last_seq=%d wall=%.1fs", self.session_id, self.status,
                     self.frames_sent, self.last_seq, time.time() - self.started_wall)

    def _register(self):
        try:
            from smip.serving import ch

            now = datetime.now(timezone.utc)
            ch.client().insert("replay_sessions", [[
                self.session_id, self.spec.match_id, self.meta["source"], self.meta["sport"], float(self._speed),
                self.spec.seed, json.dumps(asdict(self.spec.faults)), self.status, self.frames_sent, self.last_seq,
                datetime.fromtimestamp(self.started_wall, timezone.utc), now, self.session_base,
                f"attempt={self.attempt}"]],
                column_names=["session_id", "match_id", "source", "sport", "speed", "seed", "faults", "status",
                              "frames_sent", "last_seq", "started_at", "updated_at", "session_base", "note"])
        except Exception as exc:  # registry is observability only; never block the replay
            log.debug("session registry unavailable: %s", exc)


def make_producer():
    from confluent_kafka import Producer

    return Producer({
        "bootstrap.servers": get_settings().kafka_bootstrap,
        "enable.idempotence": True,     # no broker-side duplicates from producer retries
        "acks": "all",
        "linger.ms": 20,
        "compression.type": "zstd",
        "message.max.bytes": 4_000_000,
        "queue.buffering.max.messages": 200_000,
    })
