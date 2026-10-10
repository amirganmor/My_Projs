"""Normalized (silver-input) parquet contracts written by source adapters.

These column lists are enforced by ``validate_tracking_frame`` before anything is written, so
every adapter produces an identical long-form layout that replay, batch backfill and tests share.
"""

from __future__ import annotations

import pyarrow as pa

FRAMES_SCHEMA = pa.schema([
    ("sequence", pa.int64()),
    ("source_frame_id", pa.int64()),
    ("period", pa.int16()),
    ("source_clock", pa.string()),
    ("period_elapsed_ms", pa.int64()),
    ("match_elapsed_ms", pa.int64()),
    ("physical_time_ms", pa.int64()),
    ("source_timestamp", pa.string()),
    ("shot_clock_s", pa.float64()),
    ("n_players", pa.int32()),
    ("n_players_detected", pa.int32()),
    ("has_ball", pa.bool_()),
    ("possession_team_id", pa.string()),
    ("possession_player_id", pa.string()),
    ("source_segment", pa.string()),        # e.g. SportVU event id the moment was taken from
    ("frame_quality_flags", pa.string()),
])

TRACKING_SCHEMA = pa.schema([
    ("sequence", pa.int64()),              # canonical, gapless over retained frames
    ("source_frame_id", pa.int64()),
    ("period", pa.int16()),
    ("source_clock", pa.string()),
    ("period_elapsed_ms", pa.int64()),
    ("match_elapsed_ms", pa.int64()),
    ("physical_time_ms", pa.int64()),
    ("source_timestamp", pa.string()),
    ("entity_type", pa.string()),
    ("source_player_id", pa.string()),
    ("canonical_player_id", pa.string()),
    ("team_id", pa.string()),
    ("jersey", pa.string()),
    ("x_src", pa.float64()),
    ("y_src", pa.float64()),
    ("z_src", pa.float64()),
    ("x_m", pa.float64()),
    ("y_m", pa.float64()),
    ("z_m", pa.float64()),
    ("x_att", pa.float64()),
    ("y_att", pa.float64()),
    ("is_detected", pa.bool_()),
    ("is_extrapolated", pa.bool_()),
    ("position_source", pa.string()),
    ("confidence", pa.float64()),
    ("possession_team_id", pa.string()),
    ("possession_player_id", pa.string()),
    ("frame_quality_flags", pa.string()),   # comma-separated
])

EVENTS_SCHEMA = pa.schema([
    ("event_id", pa.string()),
    ("match_id", pa.string()),
    ("period", pa.int16()),
    ("source_clock", pa.string()),
    ("match_elapsed_ms", pa.int64()),
    ("source_frame_start", pa.int64()),
    ("source_frame_end", pa.int64()),
    ("event_type", pa.string()),
    ("event_subtype", pa.string()),
    ("team_id", pa.string()),
    ("player_id", pa.string()),
    ("x_m", pa.float64()),
    ("y_m", pa.float64()),
    ("end_x_m", pa.float64()),
    ("end_y_m", pa.float64()),
    ("outcome", pa.string()),
    ("label_origin", pa.string()),
    ("coordinate_space", pa.string()),      # physical_m | standardized_105x68 | provider_units
    ("attributes_json", pa.string()),       # original provider fields preserved
])

REQUIRED_MATCH_KEYS = {
    "match_id", "source", "source_match_id", "source_revision", "sport", "competition", "season",
    "date", "home_team", "away_team", "periods", "dimensions", "sample_rate_hz", "capabilities",
    "players", "time_model", "coordinate_notes",
}


def validate_match_meta(meta: dict) -> None:
    missing = REQUIRED_MATCH_KEYS - set(meta)
    if missing:
        raise ValueError(f"match metadata missing keys: {sorted(missing)}")
    for p in meta["periods"]:
        for k in ("period", "attack_direction"):
            if k not in p:
                raise ValueError(f"period entry missing {k}: {p}")


def cast_to(table: pa.Table, schema: pa.Schema) -> pa.Table:
    """Order/cast columns to a contract schema; raises if a column is missing."""
    missing = set(schema.names) - set(table.column_names)
    if missing:
        raise ValueError(f"table missing columns {sorted(missing)}")
    return table.select(schema.names).cast(schema)
