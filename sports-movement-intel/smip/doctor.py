"""`smip doctor`: host + stack checks. Each check prints ok/warn/fail; only `fail` fails the command."""

from __future__ import annotations

import importlib
import shutil
import socket
import subprocess
import sys

import httpx

from smip.config import get_settings


def _port(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def _http(url: str) -> bool:
    try:
        return httpx.get(url, timeout=3).status_code < 500
    except httpx.HTTPError:
        return False


def run_doctor() -> bool:
    s = get_settings()
    results: list[tuple[str, str, str]] = []

    def check(name: str, level_if_bad: str, ok: bool, detail: str = "") -> None:
        results.append(("ok" if ok else level_if_bad, name, detail))

    check("python >= 3.10", "fail", sys.version_info >= (3, 10), sys.version.split()[0])
    for mod in ["pydantic", "pyarrow", "pandas", "numpy", "yaml", "httpx", "clickhouse_connect", "typer"]:
        try:
            importlib.import_module(mod)
            check(f"import {mod}", "fail", True)
        except ImportError as e:
            check(f"import {mod}", "fail", False, str(e))
    for mod in ["confluent_kafka", "fastapi", "py7zr", "pyiceberg", "sklearn", "mlflow", "pyspark"]:
        try:
            importlib.import_module(mod)
            check(f"import {mod}", "warn", True)
        except ImportError:
            check(f"import {mod}", "warn", False, "optional extra not installed")
    check("java (host Spark backfill)", "warn", shutil.which("java") is not None)
    docker = shutil.which("docker")
    check("docker cli", "fail", docker is not None)
    if docker:
        try:
            mem = int(subprocess.run([docker, "info", "--format", "{{.MemTotal}}"], capture_output=True, text=True,
                                     timeout=15).stdout.strip() or 0)
            check("docker VM memory >= 10 GiB (recommended 14)", "warn", mem >= 10 * 2**30, f"{mem / 2**30:.1f} GiB")
        except (subprocess.SubprocessError, ValueError):
            check("docker daemon reachable", "fail", False)
    free = shutil.disk_usage(s.data_dir.parent).free
    check("disk free >= 20 GB", "warn", free >= 20e9, f"{free / 1e9:.0f} GB")
    kh, kp = s.kafka_bootstrap.split(":")
    check("kafka broker", "warn", _port(kh, int(kp)), s.kafka_bootstrap)
    check("clickhouse /ping", "warn", _http(f"http://{s.clickhouse_host}:{s.clickhouse_port}/ping"))
    check("iceberg rest /v1/config", "warn", _http(f"{s.iceberg_rest_uri}/v1/config"))
    check("object store", "warn", _http(s.s3_endpoint))
    check("api /api/health", "warn", _http(f"{s.api_url}/api/health"))
    check("ollama (optional analyst LLM)", "warn", _http(f"{s.ollama_url}/api/tags"), "deterministic fallback if absent")
    check("raw data present", "warn", s.raw_dir.exists() and any(s.raw_dir.iterdir()), str(s.raw_dir))
    check("normalized data present", "warn", s.normalized_dir.exists() and any(s.normalized_dir.iterdir()))

    for level, name, detail in results:
        print(f"[{level:4}] {name}{'  - ' + detail if detail else ''}")
    return not any(r[0] == "fail" for r in results)
