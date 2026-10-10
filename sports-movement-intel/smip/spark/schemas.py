"""Spark schemas for Kafka envelopes and engine output kinds (mirrors smip.contracts / engine rows)."""

from __future__ import annotations

from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DoubleType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
)

S, L, D, B, I = StringType(), LongType(), DoubleType(), BooleanType(), IntegerType()


def st(*fields):
    return StructType([StructField(n, t, True) for n, t in fields])


# Envelope fields needed for validation / routing (full message stays as raw JSON string).
ENVELOPE = st(
    ("schema_version", S), ("record_type", S), ("source", S), ("source_revision", S), ("sport", S),
    ("match_id", S), ("record_id", S), ("source_frame_id", L), ("period", I), ("physical_time_ms", L),
    ("match_elapsed_ms", L), ("replay_session_id", S), ("replay_event_time", S), ("produced_at", S),
    ("sequence", L), ("attempt", I), ("end_of_stream", B), ("quality_flags", ArrayType(S)),
    ("players", ArrayType(st(("canonical_player_id", S), ("x_m", D), ("y_m", D)))),
)

KINDS = {
    "frame": st(("seq", L), ("source_frame_id", L), ("t", L), ("mel", L), ("period", I), ("clock", S),
                ("poss_team", S), ("n_players", I), ("n_detected", I), ("has_ball", B), ("flags", S),
                ("attempt", I), ("replay_event_time", S), ("produced_at", S)),
    "obs": st(("seq", L), ("t", L), ("mel", L), ("period", I), ("entity_id", S), ("entity_type", S),
              ("team_id", S), ("x_m", D), ("y_m", D), ("z_m", D), ("x_att", D), ("y_att", D), ("is_detected", B),
              ("position_source", S), ("speed_mps", D), ("accel_mps2", D), ("dist_raw_m", D), ("dist_m", D),
              ("segment_start", B), ("gap_ms", L), ("implausible", B), ("cell_x", I), ("cell_y", I)),
    "team_frame": st(("seq", L), ("t", L), ("mel", L), ("period", I), ("team_id", S), ("n_outfield", I),
                     ("n_detected", I), ("sufficient", B), ("in_possession", B), ("centroid_x", D),
                     ("centroid_y", D), ("width_m", D), ("depth_m", D), ("hull_area_m2", D),
                     ("def_line_height_m", D), ("spacing_hull_m2", D), ("mean_pairwise_m", D),
                     ("paint_count", I), ("corner_count", I), ("nearest_def_to_ball_m", D), ("offense", B)),
    "player_window": st(("entity_id", S), ("team_id", S), ("window", I), ("window_start_ms", L),
                        ("window_end_ms", L), ("is_final", B), ("distance_m", D), ("distance_raw_m", D),
                        ("active_ms", L), ("detected_ms", L), ("hi_ms", L), ("sprint_ms", L),
                        ("hi_distance_m", D), ("sprint_count", I), ("accel_count", I), ("decel_count", I),
                        ("max_speed_mps", D), ("in_poss_ms", L), ("out_poss_ms", L), ("poss_unknown_ms", L),
                        ("n_intervals", L), ("excluded_gap_ms", L), ("no_cell_ms", L), ("version", L)),
    "dwell": st(("entity_id", S), ("team_id", S), ("window", I), ("cell_x", I), ("cell_y", I), ("dwell_ms", L),
                ("is_final", B), ("version", L)),
    "team_window": st(("team_id", S), ("window", I), ("window_start_ms", L), ("window_end_ms", L),
                      ("is_final", B), ("n_frames", L), ("n_sufficient", L), ("in_possession_frames", L),
                      ("mean_centroid_x", D), ("mean_width_m", D), ("mean_depth_m", D), ("mean_hull_area_m2", D),
                      ("mean_def_line_height_m", D), ("version", L)),
    "late": st(("seq", L), ("reason", S), ("t", L), ("attempt", I)),
}

ENGINE_OUTPUT = st(("session_id", S), ("match_id", S), ("kind", S), ("payload", S))
ENGINE_STATE = st(("state", S))
