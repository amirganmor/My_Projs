"""Measured benchmarks. Only numbers produced here go into docs/BENCHMARKS.md.

* stream throughput: an unthrottled replay (speed 0) of one match; wall time from the first produce to
  the engine finalizing the session, and frames/s over that span.
* batch throughput: the same engine in-process over normalized parquet (no Kafka/Spark).
* latency: produce -> ClickHouse ``processed_at`` for a paced session (default the 20x hero session).
  Unthrottled sessions are excluded because their latency is backlog queueing.
* memory: ``docker stats`` sampled every 2 s during the stream run; peak per container.
"""

from __future__ import annotations

import json
import platform
import subprocess
import threading
import time
from datetime import datetime, timezone

from smip.config import REPO_ROOT, get_settings


def _mem_bytes(s: str) -> float:
    num = float("".join(ch for ch in s if ch.isdigit() or ch == "."))
    unit = s.lstrip("0123456789.").strip().lower()
    return num * {"b": 1, "kib": 2**10, "mib": 2**20, "gib": 2**30, "kb": 1e3, "mb": 1e6, "gb": 1e9}.get(unit, 1)


class DockerSampler(threading.Thread):
    def __init__(self, every_s: float = 2.0):
        super().__init__(daemon=True)
        self.every, self.stop_evt, self.peak, self.limit, self.cpu_peak = every_s, threading.Event(), {}, {}, {}
        self.samples = 0

    def run(self):
        while not self.stop_evt.is_set():
            try:
                out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}"],
                                     capture_output=True, text=True, timeout=20).stdout
                for line in out.splitlines():
                    r = json.loads(line)
                    name = r["Name"].removeprefix("smip-").removesuffix("-1")
                    used, lim = (x.strip() for x in r["MemUsage"].split("/"))
                    self.peak[name] = max(self.peak.get(name, 0), _mem_bytes(used))
                    self.limit[name] = _mem_bytes(lim)
                    self.cpu_peak[name] = max(self.cpu_peak.get(name, 0), float(r["CPUPerc"].rstrip("%") or 0))
                self.samples += 1
            except Exception:  # noqa: BLE001 - sampling is best effort
                pass
            self.stop_evt.wait(self.every)


def run(match_id: str = "skillcorner:1886347", latency_session: str = "demo-soccer-hero") -> dict:
    from smip.demo import wait_processed
    from smip.features.batch import run_match
    from smip.replay.session import ReplaySession, SessionSpec
    from smip.serving import ch

    sid = f"bench-{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    sampler = DockerSampler()
    sampler.start()
    t0 = time.time()
    rs = ReplaySession(SessionSpec(match_id=match_id, speed=0.0, session_id=sid))
    rs.run()
    t_produced = time.time()
    wait_processed(sid, match_id, timeout_s=3600, poll_s=2)
    t_done = time.time()
    sampler.stop_evt.set()
    sampler.join(timeout=30)
    frames = ch.query_rows("SELECT count() AS n, min(processed_at) AS first, max(processed_at) AS last "
                           "FROM frames FINAL WHERE session_id={s:String}", {"s": sid})[0]
    batches = ch.query_rows("SELECT query_name, count() AS batches, avg(duration_ms) AS avg_ms, "
                            "quantileExact(0.95)(duration_ms) AS p95_ms, sum(rows) AS rows FROM sink_ledger FINAL "
                            "WHERE committed_at >= fromUnixTimestamp64Milli({t:Int64}) GROUP BY query_name",
                            {"t": int(t0 * 1000)})
    lat = ch.query_rows(
        "SELECT count() AS n, quantileExact(0.5)(d) AS p50_ms, quantileExact(0.95)(d) AS p95_ms, "
        "quantileExact(0.99)(d) AS p99_ms, max(d) AS max_ms FROM (SELECT dateDiff('millisecond', produced_at, "
        "processed_at) AS d FROM frames FINAL WHERE session_id={s:String})", {"s": latency_session})[0]
    speed = ch.query_rows("SELECT any(speed) AS speed, any(match_id) AS match_id FROM replay_sessions FINAL "
                          "WHERE session_id={s:String}", {"s": latency_session})

    tb = time.time()
    res = run_match(match_id, session_id="bench-batch", keep={"player_window"})
    batch_s = time.time() - tb
    n_batch_frames = frames["n"]
    del res

    stream_s = t_done - t0
    out = {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": {"machine": platform.machine(), "system": f"{platform.system()} {platform.release()}",
                 "python": platform.python_version(), "docker_vm_bytes": _docker_mem()},
        "stream": {"session_id": sid, "match_id": match_id, "frames": frames["n"],
                   "produce_s": round(t_produced - t0, 1), "end_to_end_s": round(stream_s, 1),
                   "frames_per_s": round(frames["n"] / stream_s, 1),
                   "trigger_s": int(get_settings_env("SMIP_TRIGGER_SECONDS", "2")),
                   "max_offsets_per_trigger": int(get_settings_env("SMIP_MAX_OFFSETS", "2500")),
                   "sink_batches": batches},
        "batch": {"match_id": match_id, "seconds": round(batch_s, 1), "frames_per_s": round(n_batch_frames / batch_s, 1)},
        "latency": {"session_id": latency_session, "speed": speed[0]["speed"] if speed else None, **lat},
        "memory_peak_bytes": {k: int(v) for k, v in sorted(sampler.peak.items())},
        "memory_limit_bytes": {k: int(v) for k, v in sorted(sampler.limit.items())},
        "cpu_peak_percent": dict(sorted(sampler.cpu_peak.items())), "docker_samples": sampler.samples,
        "containers_after": container_health(),
    }
    d = get_settings().data_dir / "demo"
    d.mkdir(parents=True, exist_ok=True)
    (d / "bench.json").write_text(json.dumps(out, indent=2, default=str))
    (REPO_ROOT / "docs" / "BENCHMARKS.md").write_text(render(out))
    return out


def get_settings_env(name: str, default: str) -> str:
    """Value from the spark-stream container's environment (the host env does not configure Spark)."""
    try:
        env = json.loads(subprocess.run(["docker", "inspect", "smip-spark-stream-1", "--format", "{{json .Config.Env}}"],
                                        capture_output=True, text=True, timeout=10).stdout)
        return next((e.split("=", 1)[1] for e in env if e.startswith(name + "=")), default)
    except Exception:  # noqa: BLE001
        return default


def container_health() -> dict:
    """OOM-kill flag and restart count per compose container."""
    try:
        ids = subprocess.run(["docker", "ps", "-q", "--filter", "label=com.docker.compose.project=smip"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        out = subprocess.run(["docker", "inspect", "-f",
                              "{{index .Config.Labels \"com.docker.compose.service\"}} {{.State.OOMKilled}} "
                              "{{.RestartCount}}", *ids], capture_output=True, text=True, timeout=10).stdout
        return {n: {"oom_killed": o == "true", "restarts": int(r)}
                for n, o, r in (line.split() for line in out.splitlines() if line.strip())}
    except Exception:  # noqa: BLE001
        return {}


def _docker_mem() -> int | None:
    try:
        return int(subprocess.run(["docker", "info", "--format", "{{.MemTotal}}"], capture_output=True, text=True,
                                  timeout=10).stdout.strip())
    except Exception:  # noqa: BLE001
        return None


def render(b: dict) -> str:
    mib = lambda v: f"{v / 2**20:,.0f} MiB"  # noqa: E731
    s, bt, la = b["stream"], b["batch"], b["latency"]
    health = b.get("containers_after", {})

    def after(k: str) -> str:
        h = health.get(k)
        return "not checked" if h is None else f"{'OOM-killed' if h['oom_killed'] else 'no OOM'}, {h['restarts']} restarts"

    rows = "\n".join(f"| {k} | {mib(v)} | {mib(b['memory_limit_bytes'].get(k, 0))} | "
                     f"{b['cpu_peak_percent'].get(k, 0):.0f}% | {after(k)} |"
                     for k, v in b["memory_peak_bytes"].items())
    sinks = "\n".join(f"| {r['query_name']} | {r['batches']} | {r['rows']:,} | {r['avg_ms']:,.0f} | {r['p95_ms']:,.0f} |"
                      for r in s["sink_batches"])
    vm = b["host"]["docker_vm_bytes"]
    return f"""# Benchmarks

Generated by `smip bench run` at {b['measured_at']}. Every number below was measured by that command on
this machine; nothing is extrapolated. Re-run it to refresh this file.

Host: {b['host']['machine']} · {b['host']['system']} · Docker VM {vm / 2**30:.2f} GiB · Python {b['host']['python']}

## Streaming throughput (unthrottled replay)

| match | frames | produce | end-to-end (produce → engine finalized) | frames/s |
|---|---|---|---|---|
| `{s['match_id']}` | {s['frames']:,} | {s['produce_s']} s | {s['end_to_end_s']} s | {s['frames_per_s']:,} |

Spark `local[3]`, trigger {s['trigger_s']} s, `maxOffsetsPerTrigger` {s['max_offsets_per_trigger']:,}. The bottleneck is the
stateful engine query (`applyInPandasWithState` plus Iceberg and ClickHouse writes per micro-batch):

| query | micro-batches | rows written | avg batch ms | p95 batch ms |
|---|---|---|---|---|
{sinks}

## Batch engine (same code, no Kafka/Spark)

`smip.features.batch.run_match` over normalized parquet: {bt['seconds']} s, **{bt['frames_per_s']:,} frames/s**.

## Latency (paced replay)

Produce → ClickHouse `processed_at` for session `{la['session_id']}` at {la['speed']}× over {la['n']:,} frames:
p50 **{la['p50_ms']:,} ms**, p95 **{la['p95_ms']:,} ms**, p99 {la['p99_ms']:,} ms, max {la['max_ms']:,} ms.
With a 2 s trigger, a frame waits on average about one trigger interval plus the batch time.
Unthrottled sessions are excluded here because their latency measures backlog, not steady state.

## Memory and CPU per container (peak of {b['docker_samples']} `docker stats` samples during the stream run)

| container | peak memory | limit | peak CPU | after the run |
|---|---|---|---|---|
{rows}

A container at its limit (Spark's JVM heap plus Python workers grow into the cgroup) is not a failure by itself;
the last column is read from `docker inspect` after the run.

## Not measured

Multi-match concurrency, Kafka partition scaling, and anything beyond this single 8 GB Docker VM.
"""
