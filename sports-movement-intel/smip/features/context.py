"""Match context and sport configuration shared by batch and streaming feature code."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from smip.config import get_settings


@dataclass(frozen=True)
class SportConfig:
    sport: str
    feature_version: str
    reorder_window_frames: int
    max_gap_ms: int
    max_speed_player: float
    max_speed_ball: float
    ema_alpha: float
    hi_speed_mps: float
    sprint_speed_mps: float
    accel_threshold_mps2: float
    window_ms: int
    grid_nx: int
    grid_ny: int
    min_outfield_for_shape: int
    inactivity_timeout_ms: int


@dataclass(frozen=True)
class MatchContext:
    match_id: str
    sport: str
    length_m: float
    width_m: float
    team_ids: tuple[str, ...]
    goalkeepers: frozenset = field(default_factory=frozenset)
    physical_dims: bool = True
    period_offsets: tuple = ()          # ((period, offset_ms), ...) from match metadata


@lru_cache(maxsize=4)
def sport_config(sport: str, path: str | None = None) -> SportConfig:
    p = Path(path) if path else get_settings().config_dir / "sports.yaml"
    c = yaml.safe_load(p.read_text())[sport]
    return SportConfig(
        sport=sport, feature_version=c["feature_version"], reorder_window_frames=c["reorder_window_frames"],
        max_gap_ms=c["max_gap_ms"], max_speed_player=c["max_speed_mps"]["player"],
        max_speed_ball=c["max_speed_mps"]["ball"], ema_alpha=c["ema_alpha"], hi_speed_mps=c["hi_speed_mps"],
        sprint_speed_mps=c["sprint_speed_mps"], accel_threshold_mps2=c["accel_threshold_mps2"],
        window_ms=c["window_ms"], grid_nx=c["grid"]["nx"], grid_ny=c["grid"]["ny"],
        min_outfield_for_shape=c["min_outfield_for_shape"], inactivity_timeout_ms=c["inactivity_timeout_ms"],
    )


def context_from_meta(meta: dict) -> MatchContext:
    dims = meta["dimensions"]
    gks = frozenset(p["canonical_player_id"] for p in meta.get("players", []) if p.get("is_goalkeeper"))
    return MatchContext(
        match_id=meta["match_id"], sport=meta["sport"], length_m=float(dims["length_m"]),
        width_m=float(dims["width_m"]),
        team_ids=(meta["home_team"]["team_id"], meta["away_team"]["team_id"]),
        goalkeepers=gks, physical_dims=bool(dims.get("physical", True)),
        period_offsets=tuple((int(p["period"]), int(p.get("offset_ms", 0))) for p in meta["periods"]),
    )


@lru_cache(maxsize=256)
def load_match_meta(match_id: str, normalized_dir: str | None = None) -> dict:
    source, mid = match_id.split(":", 1)
    base = Path(normalized_dir) if normalized_dir else get_settings().normalized_dir
    return json.loads((base / source / mid / "match.json").read_text())
