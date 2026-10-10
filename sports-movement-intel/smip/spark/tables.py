"""Iceberg DDL for bronze / silver / gold / ops namespaces in the ``smip`` REST catalog.

Partitioning: tables are read per match, a single match is ~1M position rows (~30-40 MB zstd
parquet), so ``match_id`` identity partitioning keeps one match per partition without per-player or
per-frame partitions. Bronze is partitioned by ingest day. Streaming commits create small files;
``smip maintenance`` compacts them (rewrite_data_files) and expires snapshots.
"""

from __future__ import annotations

PROPS = ("'format-version'='2', 'write.parquet.compression-codec'='zstd', "
         "'write.target-file-size-bytes'='134217728', 'write.metadata.delete-after-commit.enabled'='true', "
         "'write.metadata.previous-versions-max'='50', 'history.expire.max-snapshot-age-ms'='604800000'")

DDL = {
    "bronze.kafka_tracking_raw": """
        topic STRING, kafka_partition INT, kafka_offset BIGINT, kafka_ts TIMESTAMP, key STRING, value STRING,
        replay_session_id STRING, match_id STRING, sequence BIGINT, valid BOOLEAN, invalid_reason STRING,
        ingested_at TIMESTAMP, batch_id BIGINT
    """, "bronze.kafka_tracking_raw#part": "days(kafka_ts)",
    "silver.tracking_frames": """
        session_id STRING, match_id STRING, seq BIGINT, source_frame_id BIGINT, t_ms BIGINT, mel_ms BIGINT,
        period INT, clock STRING, poss_team STRING, n_players INT, n_detected INT, has_ball BOOLEAN,
        flags STRING, attempt INT, replay_event_time TIMESTAMP, produced_at TIMESTAMP, processed_at TIMESTAMP,
        batch_id BIGINT, feature_version STRING
    """, "silver.tracking_frames#part": "match_id",
    "silver.tracking_positions": """
        session_id STRING, match_id STRING, seq BIGINT, t_ms BIGINT, mel_ms BIGINT, period INT,
        entity_id STRING, entity_type STRING, team_id STRING, x_m DOUBLE, y_m DOUBLE, z_m DOUBLE,
        x_att DOUBLE, y_att DOUBLE, is_detected BOOLEAN, position_source STRING, speed_mps DOUBLE,
        accel_mps2 DOUBLE, dist_raw_m DOUBLE, dist_m DOUBLE, segment_start BOOLEAN, gap_ms BIGINT,
        implausible BOOLEAN, cell_x INT, cell_y INT, batch_id BIGINT, feature_version STRING
    """, "silver.tracking_positions#part": "match_id",
    "gold.team_frame_metrics": """
        session_id STRING, match_id STRING, seq BIGINT, t_ms BIGINT, mel_ms BIGINT, period INT, team_id STRING,
        n_outfield INT, n_detected INT, sufficient BOOLEAN, in_possession BOOLEAN, centroid_x DOUBLE,
        centroid_y DOUBLE, width_m DOUBLE, depth_m DOUBLE, hull_area_m2 DOUBLE, def_line_height_m DOUBLE,
        spacing_hull_m2 DOUBLE, mean_pairwise_m DOUBLE, paint_count INT, corner_count INT,
        nearest_def_to_ball_m DOUBLE, offense BOOLEAN, batch_id BIGINT, feature_version STRING
    """, "gold.team_frame_metrics#part": "match_id",
    "gold.player_windows": """
        session_id STRING, match_id STRING, entity_id STRING, team_id STRING, window INT, window_start_ms BIGINT,
        window_end_ms BIGINT, is_final BOOLEAN, distance_m DOUBLE, distance_raw_m DOUBLE, active_ms BIGINT,
        detected_ms BIGINT, hi_ms BIGINT, sprint_ms BIGINT, hi_distance_m DOUBLE, sprint_count INT,
        accel_count INT, decel_count INT, max_speed_mps DOUBLE, in_poss_ms BIGINT, out_poss_ms BIGINT,
        poss_unknown_ms BIGINT, n_intervals BIGINT, excluded_gap_ms BIGINT, no_cell_ms BIGINT, version BIGINT,
        batch_id BIGINT, feature_version STRING
    """, "gold.player_windows#part": "match_id",
    "gold.team_windows": """
        session_id STRING, match_id STRING, team_id STRING, window INT, window_start_ms BIGINT,
        window_end_ms BIGINT, is_final BOOLEAN, n_frames BIGINT, n_sufficient BIGINT,
        in_possession_frames BIGINT, mean_centroid_x DOUBLE, mean_width_m DOUBLE, mean_depth_m DOUBLE,
        mean_hull_area_m2 DOUBLE, mean_def_line_height_m DOUBLE, version BIGINT, batch_id BIGINT,
        feature_version STRING
    """, "gold.team_windows#part": "match_id",
    "gold.spatial_dwell": """
        session_id STRING, match_id STRING, entity_id STRING, team_id STRING, window INT, cell_x INT, cell_y INT,
        dwell_ms BIGINT, is_final BOOLEAN, version BIGINT, batch_id BIGINT, feature_version STRING
    """, "gold.spatial_dwell#part": "match_id",
    "ops.quarantine": """
        detected_at TIMESTAMP, session_id STRING, match_id STRING, seq BIGINT, reason STRING, detail STRING,
        raw_value STRING, kafka_partition INT, kafka_offset BIGINT, batch_id BIGINT
    """, "ops.quarantine#part": "days(detected_at)",
    "ops.stream_stats": """
        session_id STRING, match_id STRING, emitted_at TIMESTAMP, batch_id BIGINT, stats STRING
    """, "ops.stream_stats#part": "days(emitted_at)",
}

TABLES = [k for k in DDL if "#" not in k]


def ensure_tables(spark, catalog: str = "smip") -> None:
    for ns in ("bronze", "silver", "gold", "ops"):
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {catalog}.{ns}")
    for t in TABLES:
        part = DDL.get(f"{t}#part")
        spark.sql(f"CREATE TABLE IF NOT EXISTS {catalog}.{t} ({DDL[t]}) USING iceberg "
                  f"{'PARTITIONED BY (' + part + ')' if part else ''} TBLPROPERTIES ({PROPS})")


# Engine output kind -> (iceberg table, clickhouse table, column renames)
KIND_SINKS = {
    "frame": ("silver.tracking_frames", "frames", {"t": "t_ms", "mel": "mel_ms"}),
    "obs": ("silver.tracking_positions", "positions", {"t": "t_ms", "mel": "mel_ms"}),
    "team_frame": ("gold.team_frame_metrics", "team_frames", {"t": "t_ms", "mel": "mel_ms"}),
    "player_window": ("gold.player_windows", "player_windows", {}),
    "team_window": ("gold.team_windows", "team_windows", {}),
    "dwell": ("gold.spatial_dwell", "dwell", {}),
}
