# Model card: similar-moments-knn 0.1.0

**Code:** `smip/ml/moments.py`. **API:** `GET /api/sessions/{sid}/similar?t_ms=&k=`. **Eval:** `smip ml eval`.

## What it does

Given a moment in a replay, it returns the *k* other moments in the same match whose team shapes look
most alike. It is retrieval, not prediction. There is no training step: an index is built per match from
pipeline output.

## Inputs

- Per-second team means from ClickHouse `team_frames` (physical game time), counting only frames with
  enough players for a shape.
- Features per team, in a fixed team order:
  - soccer: width, depth, hull area, defensive-line height, centroid x
  - NBA: width, depth, hull area, centroid x, spacing hull, mean pairwise distance, paint and corner counts
- For each feature: the mean over a causal 10 s window, plus a trend (last 3 s minus first 3 s).
  Features are z-scored per match.
- Anchors are placed every 2 s. Anchors with fewer than 8 valid seconds are skipped.

## Retrieval

The distance is Euclidean in z-space, with two exclusions:
- neighbours within ±30 s of the query (same period) are excluded;
- a chosen neighbour suppresses others within 30 s of it, so results are distinct passages of play.

Similarity is reported as `exp(−d / median d)`. It is a relative score, not a probability.

## Evaluation (measured, `data/demo/ml_eval_<session>.json`)

**Protocol.** Each moment is labelled with the team holding at least 60% possession over its last 3 s.
**Lift** = the share of neighbours with the query's label ÷ the chance that two random labelled moments share a label.

| session | label source | precision | random baseline | lift | valid evidence |
|---|---|---|---|---|---|
| demo-soccer-hero (SkillCorner 1886347) | provider possession | 0.754 | 0.509 | **1.48** | yes |
| demo-soccer-faults (SkillCorner 1874553) | provider possession | 0.748 | 0.521 | **1.44** | yes |
| demo-nba (SportVU 0021500492) | heuristic offense from positions | 0.985 | 0.500 | 1.97 | **no** |

The NBA number is circular. SportVU has no possession feed, so "offense" is derived from player
positions, and the centroid feature encodes those same positions. The number is reported with
`valid_evidence: false` and must not be quoted as quality.

## Limitations

- **Shape similarity is not tactical equivalence.** Two moments can match in shape while coming from different phases of play.
- **Within-match only.** z-scoring is per match, so there is no cross-match or cross-team comparison in v0.1.
- **Blind to the ball and individual roles.** Team-level geometry only.
- **Replay-time bounded.** The index includes only processed data (cached in 10 s buckets of the cursor).
- **Soccer labels depend on the provider's possession flag,** which is itself a derived annotation.

## Out of scope / next

- Cross-match retrieval with a vector store (Qdrant is in the `ai` profile but unused).
- A learned embedding (a temporal encoder).
- Human-labelled pairs for a proper precision@k.
