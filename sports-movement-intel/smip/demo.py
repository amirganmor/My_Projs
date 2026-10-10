"""Demo seed: three reproducible historical replay sessions, each verified by parity and lineage.

* ``demo-soccer-hero``   SkillCorner 1886347 (MIT, redistributable) at 20x, no faults.
* ``demo-soccer-faults`` SkillCorner 1874553 unthrottled with bounded, seeded delivery faults.
* ``demo-nba``           SportVU 0021500492 unthrottled. Local-only (license unresolved), never public.

Sessions run one after another so the streaming engine is not shared between them; this keeps the
hero session's latency numbers representative. The report is written to data/demo/seed_report.json.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import pyarrow.parquet as pq

from smip.config import get_settings
from smip.replay.frames import match_dir
from smip.replay.session import FaultConfig, ReplaySession, SessionSpec

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemoSession:
    key: str
    session_id: str
    match_id: str
    speed: float
    public: bool
    faults: FaultConfig = field(default_factory=FaultConfig)


DEMO_SESSIONS = (
    DemoSession("hero", "demo-soccer-hero", "skillcorner:1886347", 20.0, True),
    DemoSession("faults", "demo-soccer-faults", "skillcorner:1874553", 0.0, True,
                FaultConfig(duplicate_rate=0.03, delay_rate=0.01, delay_frames=5, out_of_order_rate=0.02,
                            correction_rate=0.01, malformed_rate=0.002)),
    DemoSession("nba", "demo-nba", "sportvu:0021500492", 0.0, False),
)


def public_demo() -> bool:
    return get_settings().public_demo


def visible_sessions() -> list[DemoSession]:
    return [d for d in DEMO_SESSIONS if d.public or not public_demo()]


def wait_processed(session_id: str, match_id: str, timeout_s: float = 1800, poll_s: float = 5) -> dict:
    """Block until the streaming engine has finalized the session (end-of-stream processed)."""
    from smip.serving import ch

    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        rows = ch.query_rows(
            "SELECT stats FROM stream_stats WHERE session_id={s:String} AND match_id={m:String} "
            "ORDER BY emitted_at DESC LIMIT 1", {"s": session_id, "m": match_id})
        if rows:
            last = json.loads(rows[0]["stats"])
            if last.get("ended"):
                return last
        time.sleep(poll_s)
    raise TimeoutError(f"{session_id} not finalized after {timeout_s}s (last cursor_t={last.get('cursor_t')})")


def seed(only: list[str] | None = None, skip_existing: bool = True) -> dict:
    from smip.features.parity import parity
    from smip.lakehouse import lineage
    from smip.serving import ch

    report: dict = {"generated_at": datetime.now(timezone.utc).isoformat(), "sessions": {}}
    for d in DEMO_SESSIONS:
        if only and d.key not in only:
            continue
        entry: dict = {"session_id": d.session_id, "match_id": d.match_id, "speed": d.speed,
                       "public": d.public, "faults": asdict(d.faults)}
        exists = ch.query_rows("SELECT count() AS n FROM replay_sessions FINAL WHERE session_id={s:String} "
                               "AND status='completed'", {"s": d.session_id})[0]["n"]
        t0 = time.time()
        if exists and skip_existing:
            entry["replay"] = "already completed; reused"
        else:
            resume = (get_settings().state_dir / "replay" / f"{d.session_id}.json").exists()
            rs = ReplaySession(SessionSpec(match_id=d.match_id, speed=d.speed, session_id=d.session_id,
                                           faults=d.faults, resume=resume))
            rs.run()
            entry["replay"] = {"status": rs.status, "frames_sent": rs.frames_sent, "last_seq": rs.last_seq,
                               "attempt": rs.attempt, "wall_s": round(time.time() - t0, 1)}
        stats = wait_processed(d.session_id, d.match_id)
        entry["engine_counters"] = stats.get("counters")
        entry["processed_wall_s"] = round(time.time() - t0, 1)
        entry["parity"] = parity(d.match_id, d.session_id)
        entry["lineage"] = lineage(d.session_id, d.match_id)
        n_frames = pq.ParquetFile(match_dir(d.match_id) / "frames.parquet").metadata.num_rows
        silver = entry["lineage"]["silver.tracking_frames"]["rows"]
        entry["lineage"]["source_frames"] = n_frames
        entry["ok"] = bool(entry["parity"]["ok"]) and silver == n_frames
        log.info("demo %s: parity=%s lineage_ok=%s", d.key, entry["parity"]["ok"], entry["ok"])
        report["sessions"][d.key] = entry
    report["ok"] = all(e["ok"] for e in report["sessions"].values())
    out = get_settings().data_dir / "demo" / "seed_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    prev = json.loads(out.read_text()) if out.exists() and only else {"sessions": {}}
    prev["sessions"].update(report["sessions"])
    prev.update(generated_at=report["generated_at"], ok=all(e["ok"] for e in prev["sessions"].values()))
    out.write_text(json.dumps(prev, indent=2, default=str))
    return prev
