# Model card: shape-change-pelt 0.1.0

**Code:** `smip/ml/changes.py`. **API:** `GET /api/sessions/{sid}/changes`. **Library:** `ruptures` (PELT).

## What it does

It finds points in a match where a team's shape statistics shift: for example, the block drops deeper
or the team gets wider. These points are shown as markers on the dashboard timeline, and clicking one seeks the replay.

## Method

1. Per-second team shape (same source as similar moments) is averaged into **10 s bins** of physical game time.
2. Features are z-scored per team.
3. PELT runs on each team and period separately:
   - L2 cost, `min_size` = 4 bins (40 s)
   - penalty = `1.5 · n_features · ln(n_bins)`
4. For each change point, the output lists the features whose segment means moved most, in their own
   units (the before and after segment means), plus evidence ids that point to the bins.

## Measured output (demo sessions)

| session | change points |
|---|---|
| demo-soccer-hero | 26 |
| demo-soccer-faults | 29 |
| demo-nba | 2 |

The NBA count is low because there are fewer bins per period and shape is only defined while the team is set up.

## Evaluation

There is **no ground truth**, and therefore no accuracy number. The change points are statistical shifts, not
labelled tactical events such as substitutions or formation changes. The penalty was chosen once so the
count is readable (about one per 7 minutes per team in the soccer demos), not tuned against labels.
`make verify` only checks that change points exist and that each one carries evidence.

## Limitations

- **Sensitive to the penalty and to the 40 s minimum segment.** A different choice gives a different count.
- **Offline over processed data.** Each call re-segments the prefix up to the cursor, so earlier change points can move as more data arrives.
- **Shape drops when too few players are visible.** Frames without enough players are dropped from bins, so camera-coverage gaps in SkillCorner broadcast tracking can look like changes.
