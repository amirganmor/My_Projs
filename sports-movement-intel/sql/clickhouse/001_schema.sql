-- ClickHouse serving tables. Written by the Spark streaming sink (at-least-once) and read by the API.
-- ReplacingMergeTree collapses retried inserts that share the ORDER BY key; queries resolve the
-- latest version explicitly (FINAL or argMax) because merges are asynchronous.
CREATE DATABASE IF NOT EXISTS smip;

CREATE TABLE IF NOT EXISTS smip.frames
(
    session_id String, match_id String, seq Int64, source_frame_id Int64, t_ms Int64, mel_ms Nullable(Int64),
    period Int16, clock Nullable(String), poss_team Nullable(String), n_players Int32, n_detected Int32,
    has_ball Bool, flags String, attempt Int32,
    replay_event_time Nullable(DateTime64(3, 'UTC')), produced_at Nullable(DateTime64(3, 'UTC')),
    processed_at DateTime64(3, 'UTC'), batch_id Int64
)
ENGINE = ReplacingMergeTree(processed_at)
ORDER BY (session_id, match_id, seq);

CREATE TABLE IF NOT EXISTS smip.positions
(
    session_id String, match_id String, seq Int64, t_ms Int64, mel_ms Nullable(Int64), period Int16,
    entity_id String, entity_type LowCardinality(String), team_id Nullable(String),
    x_m Float32, y_m Float32, z_m Nullable(Float32), x_att Nullable(Float32), y_att Nullable(Float32),
    is_detected Nullable(Bool), position_source LowCardinality(String),
    speed_mps Nullable(Float32), accel_mps2 Nullable(Float32), dist_m Nullable(Float32), dist_raw_m Nullable(Float32),
    segment_start Bool, gap_ms Nullable(Int64), implausible Bool, cell_x Nullable(Int16), cell_y Nullable(Int16),
    batch_id Int64
)
ENGINE = ReplacingMergeTree(batch_id)
ORDER BY (session_id, match_id, seq, entity_id);

CREATE TABLE IF NOT EXISTS smip.team_frames
(
    session_id String, match_id String, seq Int64, t_ms Int64, mel_ms Nullable(Int64), period Int16, team_id String,
    n_outfield Int32, n_detected Int32, sufficient Bool, in_possession Nullable(Bool),
    centroid_x Nullable(Float32), centroid_y Nullable(Float32), width_m Nullable(Float32), depth_m Nullable(Float32),
    hull_area_m2 Nullable(Float32), def_line_height_m Nullable(Float32),
    spacing_hull_m2 Nullable(Float32), mean_pairwise_m Nullable(Float32), paint_count Nullable(Int16),
    corner_count Nullable(Int16), nearest_def_to_ball_m Nullable(Float32), offense Nullable(Bool),
    batch_id Int64
)
ENGINE = ReplacingMergeTree(batch_id)
ORDER BY (session_id, match_id, team_id, seq);

CREATE TABLE IF NOT EXISTS smip.player_windows
(
    session_id String, match_id String, entity_id String, team_id Nullable(String), window Int32,
    window_start_ms Int64, window_end_ms Int64, is_final Bool,
    distance_m Float64, distance_raw_m Float64, active_ms Int64, detected_ms Int64, hi_ms Int64, sprint_ms Int64,
    hi_distance_m Float64, sprint_count Int32, accel_count Int32, decel_count Int32, max_speed_mps Float64,
    in_poss_ms Int64, out_poss_ms Int64, poss_unknown_ms Int64, n_intervals Int64, excluded_gap_ms Int64,
    no_cell_ms Int64, version Int64, batch_id Int64
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (session_id, match_id, entity_id, window);

CREATE TABLE IF NOT EXISTS smip.dwell
(
    session_id String, match_id String, entity_id String, team_id Nullable(String), window Int32,
    cell_x Int16, cell_y Int16, dwell_ms Int64, is_final Bool, version Int64, batch_id Int64
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (session_id, match_id, entity_id, window, cell_x, cell_y);

CREATE TABLE IF NOT EXISTS smip.team_windows
(
    session_id String, match_id String, team_id String, window Int32, window_start_ms Int64, window_end_ms Int64,
    is_final Bool, n_frames Int64, n_sufficient Int64, in_possession_frames Int64,
    mean_centroid_x Nullable(Float64), mean_width_m Nullable(Float64), mean_depth_m Nullable(Float64),
    mean_hull_area_m2 Nullable(Float64), mean_def_line_height_m Nullable(Float64), version Int64, batch_id Int64
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (session_id, match_id, team_id, window);

CREATE TABLE IF NOT EXISTS smip.stream_stats
(
    session_id String, match_id String, emitted_at DateTime64(3, 'UTC'), batch_id Int64, stats String
)
ENGINE = MergeTree
ORDER BY (session_id, match_id, emitted_at);

CREATE TABLE IF NOT EXISTS smip.quarantine
(
    detected_at DateTime64(3, 'UTC'), session_id Nullable(String), match_id Nullable(String), seq Nullable(Int64),
    reason LowCardinality(String), detail String, raw_value String, kafka_partition Nullable(Int32),
    kafka_offset Nullable(Int64), batch_id Int64
)
ENGINE = MergeTree
ORDER BY (detected_at);

CREATE TABLE IF NOT EXISTS smip.sink_ledger
(
    query_name String, batch_id Int64, sink String, rows Int64, committed_at DateTime64(3, 'UTC'),
    duration_ms Int64
)
ENGINE = ReplacingMergeTree(committed_at)
ORDER BY (query_name, batch_id, sink);

CREATE TABLE IF NOT EXISTS smip.replay_sessions
(
    session_id String, match_id String, source String, sport String, speed Float32, seed Int64, faults String,
    status LowCardinality(String), frames_sent Int64, last_seq Int64, started_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'), session_base DateTime64(3, 'UTC'), note String
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (session_id, match_id);

CREATE TABLE IF NOT EXISTS smip.predictions
(
    prediction_id String, session_id String, match_id String, model_name String, model_version String,
    feature_version String, subject_id String, t_ms Int64, value Float64, payload String,
    created_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(created_at)
ORDER BY (session_id, match_id, model_name, prediction_id);

CREATE TABLE IF NOT EXISTS smip.analysis_insights
(
    insight_id String, session_id String, match_id String, mode LowCardinality(String), question String,
    payload String, cache_key String, created_at DateTime64(3, 'UTC')
)
ENGINE = ReplacingMergeTree(created_at)
ORDER BY (match_id, session_id, insight_id);
