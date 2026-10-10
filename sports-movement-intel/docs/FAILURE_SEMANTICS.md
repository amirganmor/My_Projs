# Failure semantics

This system does **not** claim global exactly-once delivery. It claims something narrower that can be
tested: **effectively-once results per `(replay_session_id, match_id)`** in Iceberg and ClickHouse, given
Kafka's at-least-once delivery, Spark checkpoints and idempotent sinks.

## Delivery chain

| hop | guarantee | mechanism |
|---|---|---|
| replay → Kafka | at-least-once, ordered per key | idempotent producer (`acks=all`), key = `session\|match`, checkpoint every 2 s; resume re-sends from the last checkpoint with `attempt+1` |
| Kafka → Spark | at-least-once, replays uncommitted batches | Structured Streaming offsets + state store in the checkpoint directory |
| Spark → Iceberg | idempotent per micro-batch | every commit carries a snapshot summary `smip.commit=<query>:<batch_id>`; a retried batch whose tag already exists is skipped |
| Spark → ClickHouse | idempotent by key | `ReplacingMergeTree(version)` keyed on the natural key; readers use `FINAL` |
| engine | deterministic | duplicates and replays of released sequences are dropped by sequence; finalized windows never reopen |

`ops.sink_ledger` in ClickHouse records each `(query, batch_id, sink, rows)` so a retry is visible.

## Engine rules (per session state)

Frames are identified by `sequence` within a session.

| situation | outcome | counter |
|---|---|---|
| same sequence arrives again before release | ignored | `c_duplicate` |
| same sequence arrives after release | ignored (not an error) | `c_duplicate` |
| a message flagged `injected_correction` arrives while the original is still buffered | replaces it | `c_corrections_applied` |
| a correction arrives after its frame was released | not applied; logged | `c_late_correction` |
| a sequence arrives below the high-water mark but inside the buffer | released in order | `c_reordered` |
| a sequence older than the reorder buffer that was never released | not applied; logged | `c_late_beyond_reorder_buffer` |
| anything after `end_of_stream` | not applied; logged | `c_after_end` |
| a hole in the sequence after release | trajectories break at the gap | `c_sequence_gaps`, `c_missing_frames` |

**Two kinds of reordering.** Each micro-batch is sorted by `(sequence, attempt)` before ingest, so an
out-of-order frame that lands in the *same* micro-batch is fixed silently. `c_reordered` counts only
frames that cross a micro-batch boundary. For that reason, the faults session shows far fewer
"reordered" frames than it had injected.

The reorder buffer is 20 frames (2 s) for soccer and 50 frames (2 s) for NBA. Time-based partial windows
are emitted as `is_final=false`; the final row is emitted once, when the window closes.

## Malformed input

Unparseable Kafka records go to `ops.quarantine` (Iceberg and ClickHouse) with the raw payload and the
reason. They are still attributed to their session: session and match are taken from the Kafka key, and
the detail says `session_from=kafka_key`. The pipeline never guesses content for a bad record.

## Injected faults (demo session `demo-soccer-faults`)

Faults are seeded (`seed=7`) and bounded. They exist to exercise the rules above.

| fault | rate | what is sent |
|---|---|---|
| duplicate | 3% | the same frame again, immediately |
| delay | 1% | the frame 5 frames late |
| out-of-order | 2% | the frame 1 frame late |
| correction | 1% | a copy shifted +0.5 m in x first, then the true frame 3 frames later |
| malformed | 0.2% | an extra truncated JSON record (in addition to the real frame) |

Because corrections arrive inside the reorder buffer and malformed records are extras, the faults
session still reaches **exact parity** with the batch run over the clean parquet. That is the property
`make verify` checks.

## Restarts

- **Replay restart:** `smip demo seed` resumes from the replay checkpoint. Duplicated sends are absorbed by the engine.
- **Spark restart:** the checkpoint restores offsets and per-session state. Batches that were retried are skipped by the Iceberg commit tag.
- **Idle sessions:** a processing-time timeout (120 s) finalizes a session that never sent `end_of_stream`.
- **`make reset`** deletes checkpoints, the warehouse, ClickHouse volumes and demo state. Raw and normalized data are kept.
