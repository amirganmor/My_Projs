"""Canonical, versioned message and table contracts (source of truth for Python code).

Conventions
-----------
* All provider IDs are namespaced: ``<source>:<kind>:<id>`` (match ids: ``<source>:<id>``).
  No two providers' IDs are ever assumed interchangeable.
* ``x_m``/``y_m``/``z_m``: physical meters, origin at the pitch/court centre, x along the long axis.
  Only computed when the source gives physical units or documents its physical dimensions.
* ``x_att``/``y_att``: the same point rotated 180 degrees when needed so the entity's team attacks
  toward +x in that period. Direction comes from period-level metadata or a documented period-level
  inference, never from momentary movement.
* Missing values are null (None/NaN), never zero. Confidence is null unless the source provides one.
* Position provenance (``position_source``): observed | provider_extrapolated | interpolated | predicted.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CONTRACT_VERSION = "1.0.0"

Sport = Literal["soccer", "basketball"]


class EntityType(str, Enum):
    player = "player"
    ball = "ball"
    referee = "referee"
    unknown = "unknown"


class PositionSource(str, Enum):
    observed = "observed"
    provider_extrapolated = "provider_extrapolated"
    interpolated = "interpolated"
    predicted = "predicted"
    unknown = "unknown"


class ActiveStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    unknown = "unknown"


QUALITY_FLAGS = {
    "provider_extrapolated",   # is_detected false in source
    "no_ball",                 # ball coordinates missing in frame
    "few_players",             # fewer entities than expected for sport
    "duplicate_source_frame",  # same source moment seen in overlapping archive segments (resolved)
    "injected_duplicate",      # replay fault injection
    "injected_delay",
    "injected_out_of_order",
    "injected_correction",
    "no_entities",             # source frame exists but carries no entity positions
    "clock_stopped",           # basketball: game clock not advancing
    "dead_ball_gap_compressed",
}


class EntityPosition(BaseModel):
    entity_type: EntityType
    source_player_id: str | None = None        # raw provider id as string, None for ball
    canonical_player_id: str | None = None     # namespaced; "ball" entity uses "<source>:ball"
    team_id: str | None = None
    jersey: str | None = None
    x_m: float | None = None
    y_m: float | None = None
    z_m: float | None = None
    x_att: float | None = None
    y_att: float | None = None
    x_src: float | None = None
    y_src: float | None = None
    z_src: float | None = None
    is_detected: bool | None = None
    is_extrapolated: bool | None = None
    position_source: PositionSource = PositionSource.unknown
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    active_status: ActiveStatus = ActiveStatus.unknown


class Envelope(BaseModel):
    schema_version: str = CONTRACT_VERSION
    record_type: Literal["tracking_frame", "match_event", "control"]
    source: str
    source_revision: str
    sport: Sport
    match_id: str
    record_id: str                      # stable per source record: <match_id>|<kind>|<source_frame_id or event id>
    source_frame_id: int | None = None
    period: int | None = None
    source_clock: str | None = None     # original clock value as provided (string)
    match_elapsed_ms: int | None = None  # sport game-clock elapsed (may stall when clock stops)
    physical_time_ms: int | None = None  # monotonic sensor/physical time from match start
    source_timestamp: str | None = None  # original wall timestamp if provided (ISO or epoch ms string)
    replay_session_id: str
    replay_event_time: str               # ISO-8601 UTC, = session_base + physical_time_ms
    produced_at: str                     # ISO-8601 UTC wall clock at produce time
    sequence: int                        # canonical per-match order (0-based, gapless over retained frames)
    quality_flags: list[str] = Field(default_factory=list)
    attempt: int = 0                     # >0 when the replay retries an already-sent record

    @field_validator("quality_flags")
    @classmethod
    def _known_flags(cls, v: list[str]) -> list[str]:
        unknown = set(v) - QUALITY_FLAGS
        if unknown:
            raise ValueError(f"unknown quality flags {sorted(unknown)}")
        return v


class TrackingFrameMessage(Envelope):
    record_type: Literal["tracking_frame"] = "tracking_frame"
    possession_team_id: str | None = None      # provider-supplied only
    possession_player_id: str | None = None
    ball: EntityPosition | None = None
    players: list[EntityPosition] = Field(default_factory=list)
    end_of_stream: bool = False
    roster: list[str] | None = None            # canonical ids, populated on end_of_stream markers


class EventMessage(Envelope):
    record_type: Literal["match_event"] = "match_event"
    event_id: str
    event_type: str
    event_subtype: str | None = None
    team_id: str | None = None
    player_id: str | None = None
    x_m: float | None = None
    y_m: float | None = None
    end_x_m: float | None = None
    end_y_m: float | None = None
    outcome: str | None = None
    label_origin: Literal["provider", "provider_derived", "heuristic", "manual"] = "provider"


class ControlMessage(BaseModel):
    schema_version: str = CONTRACT_VERSION
    record_type: Literal["control"] = "control"
    command: Literal["start", "pause", "resume", "speed", "stop", "seek_new_session"]
    replay_session_id: str
    match_id: str | None = None
    source: str | None = None
    speed: float | None = None
    faults: dict | None = None
    seed: int | None = None
    issued_at: str
