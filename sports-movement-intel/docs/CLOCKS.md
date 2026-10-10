# Clocks

Four clocks exist and they are never mixed.

| clock | field | source | used for |
|---|---|---|---|
| source / game clock | `period`, `source_clock`, `match_elapsed_ms` | provider data, unchanged by replay | display, period logic |
| physical time | `physical_time_ms` | adapter (see below) | kinematics, windows, cutoffs |
| replay event time | `replay_event_time = session_base + physical_time_ms` | replay | Kafka payload; independent of speed and pauses |
| processing time | `produced_at`, Kafka timestamp, `processed_at` | wall clock | latency and freshness only |

## Physical time per source

- **SkillCorner (10 Hz):** frames are video frames; `physical_time_ms` = cumulative in-period time from
  observed period start frames; halftime is excluded. The UI shows the conventional clock (period 2 starts at 45:00).
- **Metrica (25 Hz):** frame index / 25 per period, offsets cumulative.
- **SportVU (25 Hz):** sensor epoch minus the first moment. It keeps running during stoppages, so it is **not**
  the game clock. `match_elapsed_ms` is the elapsed game clock and stalls while the clock is stopped
  (`clock_stopped` flag). The UI shows `Q2 +03:12` = sensor time since the quarter's first tracked moment.

## NBA score on the replay timeline

Play-by-play gives each scoring event as (period, remaining game clock). `smip sources scores` converts
that to the same elapsed-game-clock scale as `match_elapsed_ms`, then places it at the first tracked
frame in that period whose game clock has reached it. Points scored while the clock is stopped (free
throws) therefore appear when the stoppage begins. Events inside a tracking gap appear at the first
frame after it, and are flagged `tracked: false` in `scores.json`.

## Why windows are identical at any speed

Windows are keyed on `physical_time_ms` (`window = period*10000 + floor(t_in_period / 60 s)`), never on
wall time. A 60-second window contains the same frames at 0.5×, 20× or unthrottled, and after pauses or
speed changes. The replay scheduler re-anchors on speed change or resume; it only affects *when* a
frame is sent. NBA dead-ball gaps above 2 s are compressed for scheduling only (flag
`dead_ball_gap_compressed`); their event time is unchanged.

## Cutoffs

"Replay-time" answers (heatmaps, analyst, similar moments, change points) never read past the engine's
processed cursor `cursor_t` (max released `physical_time_ms`). The analyst additionally clamps to the UI
playhead (`as_of_ms`). Aggregates over 60 s windows only include windows whose `window_end_ms` is at or
before the cutoff.
