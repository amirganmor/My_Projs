"""Normalize downloaded raw assets into canonical per-match parquet (data/normalized/<source>/<id>/)."""

from __future__ import annotations

import importlib
import json
import logging
import traceback
from pathlib import Path

from smip.config import get_settings
from smip.sources import registry
from smip.sources.adapters.common import write_normalized

log = logging.getLogger(__name__)


TRACKING_ADAPTERS = ("skillcorner", "metrica", "sportvu")
EVENT_ADAPTERS = ("statsbomb", "wyscout")


def _load(names) -> dict:
    mods = {}
    for n in names:
        try:
            mods[n] = importlib.import_module(f"smip.sources.adapters.{n}")
        except ImportError as exc:
            log.warning("adapter %s unavailable: %s", n, exc)
    return mods


def _tracking_sources():
    return _load(TRACKING_ADAPTERS)


def _event_sources():
    return _load(EVENT_ADAPTERS)


def _normalized_raw_paths(root: Path) -> set[str]:
    """File names of raw assets already normalized under ``root``."""
    names: set[str] = set()
    for p in root.glob("*/match.json"):
        try:
            meta = json.loads(p.read_text())
            names |= {Path(a["path"]).name for a in (meta.get("provenance") or {}).get("raw_assets", [])}
        except (ValueError, KeyError, TypeError):
            continue
    return names


def normalize_all(only: list[str] | None = None, match_ids: list[str] | None = None, force: bool = False) -> dict:
    s = get_settings()
    report: dict = {}
    for name, mod in _tracking_sources().items():
        if only and name not in only:
            continue
        rev = registry.source(name)["pinned_revision"]
        found = mod.find_matches(s.raw_dir, rev)
        res = report.setdefault(name, {"found": len(found), "normalized": [], "skipped": [], "failed": {}})
        done_from = _normalized_raw_paths(s.normalized_dir / name)
        for mid, path in found.items():
            if match_ids and mid not in match_ids:
                continue
            out = s.normalized_dir / name / mid
            # raw keys can differ from the output id (SportVU: archive file name vs game id)
            if ((out / "match.json").exists() or Path(path).name in done_from) and not force:
                res["skipped"].append(mid)
                continue
            try:
                nm = mod.normalize(path, rev)
                write_normalized(nm, s.normalized_dir, s.raw_dir)
                res["normalized"].append(mid)
                log.info("normalized %s:%s frames=%d rows=%d", name, mid, len(nm.frames["sequence"]),
                         len(nm.tracking["sequence"]))
            except Exception as exc:  # one bad match must not stop the others
                log.error("normalize %s:%s failed: %s", name, mid, exc)
                res["failed"][mid] = f"{exc.__class__.__name__}: {exc}"
                log.debug(traceback.format_exc())
    for name, mod in _event_sources().items():
        if only and name not in only:
            continue
        try:
            report[name] = mod.normalize_corpus(s.raw_dir, s.normalized_dir, force=force)
        except FileNotFoundError as exc:
            report[name] = {"status": "not_downloaded", "detail": str(exc)}
        except Exception as exc:
            log.error("normalize %s failed: %s", name, exc)
            report[name] = {"status": "failed", "error": f"{exc.__class__.__name__}: {exc}"}
    return report
