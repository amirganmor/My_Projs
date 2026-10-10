"""End-to-end release gate (`make verify`). Prints PASS/FAIL per check and records the output.

The output is written to data/demo/verify.json and embedded verbatim in docs/STATUS.md between the
``<!-- verify:begin -->`` and ``<!-- verify:end -->`` markers.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone

from smip.config import REPO_ROOT, get_settings

RESULTS: list[dict] = []
LINES: list[str] = []


def check(name: str, fn: Callable[[], tuple[bool, str]]) -> bool:
    t0 = time.time()
    try:
        ok, detail = fn()
    except Exception as exc:  # noqa: BLE001 - a crashing check is a failing check
        ok, detail = False, f"{type(exc).__name__}: {str(exc)[:300]}"
    line = f"{'PASS' if ok else 'FAIL'}  {name:44} {detail}  ({time.time() - t0:.1f}s)"
    print(line, flush=True)
    LINES.append(line)
    RESULTS.append({"check": name, "pass": ok, "detail": detail, "seconds": round(time.time() - t0, 1)})
    return ok


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _run(cmd: list[str], cwd=REPO_ROOT, timeout=900) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "NO_COLOR": "1"})
    r.stdout = ANSI.sub("", r.stdout)
    return r


def _http(url: str, timeout=5) -> int:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status


# ------------------------------------------------------------------ checks
def unit_tests():
    r = _run([sys.executable, "-m", "pytest", "-rN"])
    summary = [ln for ln in r.stdout.splitlines() if re.search(r"\d+ (passed|failed|error)", ln)]
    return r.returncode == 0, (summary or r.stdout.strip().splitlines() or [""])[-1].strip("= ")


def lint():
    r = _run([str(REPO_ROOT / ".venv" / "bin" / "ruff"), "check", "smip", "tests", "dags"])
    return r.returncode == 0, (r.stdout.strip().splitlines() or ["ok"])[-1]


def stack_health():
    s = get_settings()
    from confluent_kafka.admin import AdminClient

    from smip.serving import ch

    status = {}
    status["clickhouse"] = ch.query_rows("SELECT 1 AS ok")[0]["ok"] == 1
    topics = AdminClient({"bootstrap.servers": s.kafka_bootstrap}).list_topics(timeout=10).topics
    status["kafka"] = "smip.tracking.v1" in topics
    status["iceberg_rest"] = _http(s.iceberg_rest_uri + "/v1/config") == 200
    status["api"] = json.loads(urllib.request.urlopen(s.api_url + "/api/health", timeout=5).read())["status"] == "ok"
    status["spark_ui"] = _http("http://127.0.0.1:14040/api/v1/applications") == 200
    import socket

    with socket.create_connection(("127.0.0.1", 17070), timeout=3):
        status["objectstore"] = True
    return all(status.values()), " ".join(f"{k}={'up' if v else 'DOWN'}" for k, v in status.items())


def parity_for(session_id: str, match_id: str):
    from smip.features.parity import parity

    rep = parity(match_id, session_id)
    t = rep["tables"]
    return rep["ok"], " ".join(f"{k}={v['stream_rows']}/{v['batch_rows']}" for k, v in t.items())


def lineage_for(session_id: str, match_id: str):
    import pyarrow.parquet as pq

    from smip.lakehouse import lineage
    from smip.replay.frames import match_dir

    lin = lineage(session_id, match_id)
    src = pq.ParquetFile(match_dir(match_id) / "frames.parquet").metadata.num_rows
    silver = lin["silver.tracking_frames"]["rows"]
    gold = lin["gold.player_windows"]["final_rows"]
    ok = silver == src and lin["bronze"]["valid"] >= src and gold > 0
    return ok, f"source={src} bronze_valid={lin['bronze']['valid']} silver={silver} gold_final_player_windows={gold}"


def _stats(session_id: str, match_id: str) -> dict:
    from smip.serving import ch

    row = ch.query_rows("SELECT stats FROM stream_stats WHERE session_id={s:String} AND match_id={m:String} "
                        "ORDER BY emitted_at DESC LIMIT 1", {"s": session_id, "m": match_id})
    return json.loads(row[0]["stats"]) if row else {}


def fault_counters():
    from smip.serving import ch

    st = _stats("demo-soccer-faults", "skillcorner:1874553")
    q = ch.query_rows("SELECT count() AS n FROM quarantine WHERE session_id='demo-soccer-faults'")[0]["n"]
    dup, corr = st.get("c_duplicate", 0), st.get("c_corrections_applied", 0)
    return dup > 0 and corr > 0 and q > 0 and st.get("ended"), f"duplicates={dup} corrections={corr} quarantined={q}"


def hero_clean():
    from smip.serving import ch

    st = _stats("demo-soccer-hero", "skillcorner:1886347")
    q = ch.query_rows("SELECT count() AS n FROM quarantine WHERE session_id='demo-soccer-hero'")[0]["n"]
    late = st.get("c_late_beyond_reorder_buffer", 0) + st.get("c_after_end", 0)
    return st.get("c_duplicate", 0) == 0 and q == 0 and late == 0, \
        f"duplicates={st.get('c_duplicate', 0)} quarantined={q} late={late} frames={st.get('c_frames_released')}"


def analyst_eval():
    from smip.analyst.eval import run_eval

    rep = run_eval("demo-soccer-hero", "skillcorner:1886347")
    failed = [c["question"] for c in rep["cases"] if not c["pass"]]
    return not failed, f"{rep['passed']}/{rep['total']} passed" + (f"; failed: {failed}" if failed else "")


def ml_eval():
    from smip.ml import changes, moments

    out = []
    ok = True
    for sid, mid in (("demo-soccer-hero", "skillcorner:1886347"), ("demo-soccer-faults", "skillcorner:1874553")):
        ev = moments.evaluate(moments.build_index(sid, mid))
        n = len(changes.detect(sid, mid)["changes"])
        ok &= (ev.get("lift") or 0) > 1.2 and n > 0
        out.append(f"{sid.split('-')[-1]}: lift={ev.get('lift')} changes={n}")
    return ok, "; ".join(out)


def public_demo_guard():
    os.environ["SMIP_PUBLIC_DEMO"] = "1"
    try:
        from fastapi.testclient import TestClient

        from smip.serving.api import app

        c = TestClient(app)
        cat = c.get("/api/catalog").json()
        sources = sorted({m["source"] for m in cat["matches"]})
        hidden = c.get("/api/matches/sportvu:0021500492").status_code
        frames = c.get("/api/sessions/demo-nba/frames", params={"match_id": "sportvu:0021500492"}).status_code
        visible = c.get("/api/matches/skillcorner:1886347").status_code
        ok = sources == ["skillcorner"] and hidden == 404 and frames == 404 and visible == 200
        return ok, f"catalog sources={sources} nba_meta={hidden} nba_frames={frames} skillcorner_meta={visible}"
    finally:
        os.environ.pop("SMIP_PUBLIC_DEMO", None)


def ui_build():
    r = _run(["npm", "run", "build"], cwd=REPO_ROOT / "frontend", timeout=300)
    m = re.search(r"built in [\d.]+m?s", r.stdout)
    return r.returncode == 0, m.group(0) if m else (r.stderr.strip().splitlines() or ["failed"])[-1]


def main() -> int:
    started = datetime.now(timezone.utc)
    print(f"smip verify · {started:%Y-%m-%d %H:%M UTC}", flush=True)
    check("unit tests (synthetic fixtures)", unit_tests)
    check("ruff lint", lint)
    check("stack health", stack_health)
    for sid, mid in (("demo-soccer-hero", "skillcorner:1886347"), ("demo-soccer-faults", "skillcorner:1874553"),
                     ("demo-nba", "sportvu:0021500492")):
        check(f"parity batch=stream {sid}", lambda s=sid, m=mid: parity_for(s, m))
        check(f"lineage kafka→iceberg {sid}", lambda s=sid, m=mid: lineage_for(s, m))
    check("fault session counters", fault_counters)
    check("hero session clean", hero_clean)
    check("analyst eval", analyst_eval)
    check("similar moments lift + change points", ml_eval)
    check("public demo guard (SMIP_PUBLIC_DEMO=1)", public_demo_guard)
    check("UI build", ui_build)
    passed = sum(r["pass"] for r in RESULTS)
    summary = f"{passed}/{len(RESULTS)} checks passed"
    print(summary)
    LINES.append(summary)
    out = {"started_at": started.isoformat(timespec="seconds"), "results": RESULTS, "passed": passed,
           "total": len(RESULTS)}
    d = get_settings().data_dir / "demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "verify.json").write_text(json.dumps(out, indent=2))
    _record(started)
    return 0 if passed == len(RESULTS) else 1


def _record(started: datetime) -> None:
    status = REPO_ROOT / "docs" / "STATUS.md"
    if not status.exists():
        return
    body = f"<!-- verify:begin -->\n```text\n$ make verify   # {started:%Y-%m-%d %H:%M UTC}\n" + "\n".join(LINES) + \
        "\n```\n<!-- verify:end -->"
    txt = status.read_text()
    txt = re.sub(r"<!-- verify:begin -->.*<!-- verify:end -->", lambda _: body, txt, flags=re.S)
    status.write_text(txt)


if __name__ == "__main__":
    raise SystemExit(main())
