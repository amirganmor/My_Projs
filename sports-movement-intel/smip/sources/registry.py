"""Loads the human-reviewed source registry (config/sources.yaml)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from smip.config import get_settings

ACCESS_STATUSES = {"verified_download", "discovered_only", "blocked", "requires_registration", "excluded"}


@lru_cache(maxsize=1)
def load_registry(path: str | None = None) -> dict:
    p = Path(path) if path else get_settings().config_dir / "sources.yaml"
    reg = yaml.safe_load(p.read_text())
    for name, src in reg["sources"].items():
        status = src.get("access_status")
        if status not in ACCESS_STATUSES:
            raise ValueError(f"source {name}: invalid access_status {status!r}")
    return reg


def source(name: str) -> dict:
    reg = load_registry()
    if name not in reg["sources"]:
        raise KeyError(f"unknown source {name!r}; known: {sorted(reg['sources'])}")
    return reg["sources"][name]


def profile(name: str) -> dict:
    reg = load_registry()
    if name not in reg["profiles"]:
        raise KeyError(f"unknown profile {name!r}; known: {sorted(reg['profiles'])}")
    return reg["profiles"][name]
