"""Resumable, checksum-verified HTTP fetching with retry/backoff and per-host rate limiting.

Original bytes are retained under data/raw/<source>/<revision>/<relative path>. Every
completed download appends an asset record to data/catalog/assets.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "smip-research-downloader/0.1 (+https://www.youtube.com/@AmirBuildsData)"
LFS_PREFIX = b"version https://git-lfs.github.com/spec/v1"


class FetchError(RuntimeError):
    pass


class ChecksumMismatch(FetchError):
    pass


class BudgetExceeded(FetchError):
    pass


@dataclass
class AssetRecord:
    source: str
    revision: str
    url: str
    local_path: str
    size_bytes: int
    sha256: str
    retrieved_at: str
    expected_checksum: str | None = None
    checksum_algo: str | None = None
    lfs: bool = False


class RateLimiter:
    def __init__(self, min_interval_s: float = 0.25):
        self.min_interval_s = min_interval_s
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, url: str) -> None:
        host = urlparse(url).netloc
        with self._lock:
            now = time.monotonic()
            delay = self._last.get(host, 0.0) + self.min_interval_s - now
            if delay > 0:
                time.sleep(delay)
            self._last[host] = time.monotonic()


def file_digest(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Fetcher:
    """Downloads with resume (HTTP Range), retries and a global byte budget."""

    def __init__(
        self,
        raw_dir: Path,
        catalog_dir: Path,
        byte_budget: int | None = None,
        max_retries: int = 5,
        backoff_s: float = 1.5,
        timeout_s: float = 120.0,
        rate_limiter: RateLimiter | None = None,
    ):
        self.raw_dir = raw_dir
        self.catalog_dir = catalog_dir
        self.byte_budget = byte_budget
        self.bytes_fetched = 0
        self.max_retries = max_retries
        self.backoff_s = backoff_s
        self.rate = rate_limiter or RateLimiter()
        self.client = httpx.Client(
            follow_redirects=True, timeout=timeout_s, headers={"User-Agent": USER_AGENT}
        )
        self.catalog_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ helpers
    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, url: str, **kw) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self.rate.wait(url)
            try:
                resp = self.client.request(method, url, **kw)
                if resp.status_code in (429, 500, 502, 503, 504):
                    retry_after = float(resp.headers.get("Retry-After", 0) or 0)
                    raise FetchError(f"HTTP {resp.status_code} for {url}") if attempt == self.max_retries - 1 else _Retry(retry_after)
                return resp
            except _Retry as r:
                time.sleep(max(r.after, self.backoff_s * (2**attempt)))
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                time.sleep(self.backoff_s * (2**attempt))
        raise FetchError(f"giving up on {url}: {last_exc}")

    def get_json(self, url: str, cache_path: Path | None = None):
        if cache_path and cache_path.exists():
            return json.loads(cache_path.read_text())
        resp = self._request("GET", url)
        if resp.status_code != 200:
            raise FetchError(f"HTTP {resp.status_code} for {url}")
        data = resp.json()
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(data))
        return data

    def get_bytes(self, url: str) -> bytes:
        resp = self._request("GET", url)
        if resp.status_code != 200:
            raise FetchError(f"HTTP {resp.status_code} for {url}")
        return resp.content

    def head_size(self, url: str) -> int | None:
        resp = self._request("HEAD", url)
        if resp.status_code >= 400:
            return None
        cl = resp.headers.get("Content-Length")
        return int(cl) if cl else None

    # ----------------------------------------------------------------- download
    def download(
        self,
        source: str,
        revision: str,
        url: str,
        rel_path: str,
        expected: str | None = None,
        algo: str = "sha256",
        expected_size: int | None = None,
        lfs: bool = False,
    ) -> AssetRecord:
        dest = self.raw_dir / source / revision / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if expected is None or file_digest(dest, algo) == expected:
                return self._record(source, revision, url, dest, expected, algo, lfs, write=False)
            log.warning("checksum mismatch on cached %s, re-downloading", dest)
            dest.unlink()

        if (self.byte_budget is not None and expected_size is not None
                and self.bytes_fetched + expected_size > self.byte_budget):
            raise BudgetExceeded(f"{rel_path} ({expected_size} B) would exceed byte budget {self.byte_budget}")

        part = dest.with_suffix(dest.suffix + ".part")
        for attempt in range(self.max_retries):
            offset = part.stat().st_size if part.exists() else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            self.rate.wait(url)
            try:
                with self.client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 416:  # already complete
                        break
                    if resp.status_code not in (200, 206):
                        if resp.status_code in (429, 500, 502, 503, 504):
                            raise httpx.TransportError(f"HTTP {resp.status_code}")
                        raise FetchError(f"HTTP {resp.status_code} for {url}")
                    mode = "ab" if resp.status_code == 206 else "wb"
                    with part.open(mode) as f:
                        for chunk in resp.iter_bytes(1 << 20):
                            f.write(chunk)
                            self.bytes_fetched += len(chunk)
                            if self.byte_budget is not None and self.bytes_fetched > self.byte_budget:
                                raise BudgetExceeded(f"byte budget {self.byte_budget} exceeded during {rel_path}")
                break
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                log.warning("download interrupted (%s), attempt %d; will resume", exc, attempt + 1)
                time.sleep(self.backoff_s * (2**attempt))
        else:
            raise FetchError(f"giving up on {url}")

        if expected is not None:
            got = file_digest(part, algo)
            if got != expected:
                part.unlink()
                raise ChecksumMismatch(f"{rel_path}: expected {algo} {expected}, got {got}")
        part.rename(dest)
        return self._record(source, revision, url, dest, expected, algo, lfs, write=True)

    def _record(self, source, revision, url, dest: Path, expected, algo, lfs, write: bool) -> AssetRecord:
        rec = AssetRecord(
            source=source,
            revision=revision,
            url=url,
            local_path=str(dest.relative_to(self.raw_dir)),
            size_bytes=dest.stat().st_size,
            sha256=file_digest(dest, "sha256"),
            retrieved_at=datetime.fromtimestamp(dest.stat().st_mtime, tz=timezone.utc).isoformat(),
            expected_checksum=expected,
            checksum_algo=algo if expected else None,
            lfs=lfs,
        )
        if write:
            with (self.catalog_dir / "assets.jsonl").open("a") as f:
                f.write(json.dumps(asdict(rec)) + "\n")
        return rec


class _Retry(Exception):
    def __init__(self, after: float):
        self.after = after


def parse_lfs_pointer(content: bytes) -> dict | None:
    if not content.startswith(LFS_PREFIX):
        return None
    fields = dict(line.split(" ", 1) for line in content.decode().strip().splitlines() if " " in line)
    oid = fields.get("oid", "")
    return {"oid": oid.split(":", 1)[1] if ":" in oid else oid, "size": int(fields.get("size", 0))}


def load_asset_index(catalog_dir: Path) -> dict[str, AssetRecord]:
    """Latest record per local_path."""
    idx: dict[str, AssetRecord] = {}
    path = catalog_dir / "assets.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                rec = AssetRecord(**json.loads(line))
                idx[rec.local_path] = rec
    return idx
