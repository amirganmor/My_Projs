# Metric registry

Thresholds live in `config/sports.yaml` and are versioned (`feature_version`, e.g. `soccer-1.0.0+engine-1.0.0`).
They are conventions, not physiological truths. Changing one requires a version bump.

## Kinematics (per entity, per consecutive frame pair)

| metric | definition | caveats |
|---|---|---|
| segment | consecutive observations in the same period with `0 < dt ≤ max_gap_ms` (soccer 500 ms, NBA 200 ms) | a larger gap breaks the trajectory; the gap is counted in `excluded_gap_ms` |
| implausible jump | raw displacement / dt > max speed (player 12.5 m/s soccer, 10.5 m/s NBA; ball 45 / 30) | the step is dropped, counted in `c_implausible_jumps` |
| smoothed position | causal EMA, α = 0.5 (soccer) / 0.35 (NBA) | causal, so batch and stream agree; lags true position slightly |
| `distance_m` | sum of smoothed step lengths inside segments | `distance_raw_m` (unsmoothed) is kept for sensitivity |
| `speed_mps` | smoothed step / dt | includes provider-extrapolated positions (flagged) |
| `hi_distance_m`, `hi_ms` | distance / time with speed ≥ 5.5 m/s (soccer) or 4.5 m/s (NBA) | |
| `sprint_count` | entries into speed ≥ 7.0 m/s (NBA 6.0) after ≥ 1 s below the threshold | |
| `max_speed_mps` | max smoothed speed | a single-frame artefact can inflate it; implausible jumps are already dropped |
| `detected_ms` | time where both endpoints of a step were directly detected (SkillCorner `is_detected`) | SportVU and Metrica provide no flag: "not provided" |

## Windows (60 s, physical time)

| table | key | contents | finalization |
|---|---|---|---|
| `player_windows` | entity, window | distance, active, detected, HSR, sprints, accel/decel counts, max speed, in/out-of-possession time, excluded gaps | when released time passes `window_end + max_gap_ms`, or the period changes |
| `team_windows` | team, window | means of width, depth, hull area, defensive line, centroid over frames with enough players | when a frame enters a later window |
| `spatial_dwell` | entity, window, cell | time-weighted occupancy on a 21×13 (soccer) / 19×10 (NBA) attack-normalized grid | with the player window |

Rows are emitted as partial (`is_final=false`) while a window is open and once more as final. Readers use
`FINAL` and filter on `is_final` where a complete window is required. Reconciliation invariant per player:
`sum(dwell_ms) = active_ms − no_cell_ms`.

## Team shape (per frame, outfield players, attack-normalized: the team attacks +x)

| metric | definition |
|---|---|
| `width_m` | max(y) − min(y) |
| `depth_m` | max(x) − min(x) |
| `hull_area_m2` | convex hull area |
| `def_line_height_m` (soccer) | mean x of the 4 deepest outfield players + L/2, i.e. metres from own goal line (heuristic) |
| `centroid_x/y` | mean position |
| `sufficient` | at least 8 (soccer) / 5 (NBA) players present; otherwise shape is not computed |

Basketball adds `spacing_hull_m2`, `mean_pairwise_m`, `paint_count` and `corner_count` for the offense, plus
`nearest_def_to_ball_m` for the defense. SportVU has no possession feed, so "offense" is the team with at least 60% of its
players in its attacking half. This is a heuristic, and it is flagged as such.

## Dashboard-only geometry (not stored)

- **Voronoi**: nearest-player regions on a 1.5 m (soccer) / 0.6 m (NBA) grid from the current frame. This is
  geometric Voronoi, **not pitch control**: no velocities, reaction times or ball travel.
- **Hulls / defensive line / trails** are drawn from the served positions of the current and last 3 s of frames;
  nothing is interpolated.
