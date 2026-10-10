"""Replay service: consumes ``smip.control.v1`` commands and runs concurrent replay sessions."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from smip.config import get_settings
from smip.replay.session import FaultConfig, ReplaySession, SessionSpec

log = logging.getLogger(__name__)
CONTROL_TOPIC = "smip.control.v1"


def send_control(command: str, session_id: str, **kw) -> dict:
    from confluent_kafka import Producer

    msg = {"schema_version": "1.0.0", "record_type": "control", "command": command,
           "replay_session_id": session_id, "issued_at": datetime.now(timezone.utc).isoformat(), **kw}
    p = Producer({"bootstrap.servers": get_settings().kafka_bootstrap})
    p.produce(CONTROL_TOPIC, key=session_id.encode(), value=json.dumps(msg).encode())
    p.flush(10)
    return msg


def serve() -> None:
    from confluent_kafka import Consumer

    c = Consumer({"bootstrap.servers": get_settings().kafka_bootstrap, "group.id": "smip-replay-service",
                  "auto.offset.reset": "latest", "enable.auto.commit": True})
    c.subscribe([CONTROL_TOPIC])
    sessions: dict[str, ReplaySession] = {}
    log.info("replay service listening on %s", CONTROL_TOPIC)
    while True:
        m = c.poll(0.5)
        for sid in [s for s, rs in sessions.items() if rs.thread and not rs.thread.is_alive()]:
            sessions.pop(sid)
        if m is None or m.error():
            continue
        try:
            cmd = json.loads(m.value())
            sid = cmd["replay_session_id"]
            op = cmd["command"]
            if op == "start":
                if sid in sessions:
                    log.warning("session %s already running", sid)
                    continue
                spec = SessionSpec(match_id=cmd["match_id"], speed=float(cmd.get("speed") or 1.0), session_id=sid,
                                   seed=int(cmd.get("seed") or 7), faults=FaultConfig(**(cmd.get("faults") or {})),
                                   resume=bool(cmd.get("resume", False)))
                sessions[sid] = ReplaySession(spec).start_thread()
            elif sid in sessions:
                rs = sessions[sid]
                if op == "pause":
                    rs.pause()
                elif op == "resume":
                    rs.resume_playback()
                elif op == "speed":
                    rs.set_speed(float(cmd["speed"]))
                elif op == "stop":
                    rs.stop()
            else:
                log.warning("control %s for unknown session %s", op, sid)
        except Exception as exc:
            log.exception("bad control message: %s", exc)
        time.sleep(0.01)
