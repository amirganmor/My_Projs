# Status: v0.1 (stable presentable release)

Everything below was run on one machine: Apple M3, Docker VM 7.65 GiB. The block between the markers is
rewritten by `make verify`. Do not edit it by hand.

## Verification gate (`make verify`)

<!-- verify:begin -->
```text
$ make verify   # 2026-09-29 16:21 UTC
PASS  unit tests (synthetic fixtures)              33 passed in 6.95s  (7.5s)
PASS  ruff lint                                    All checks passed!  (0.0s)
PASS  stack health                                 clickhouse=up kafka=up iceberg_rest=up api=up spark_ui=up objectstore=up  (2.4s)
PASS  parity batch=stream demo-soccer-hero         player_windows=2179/2179 team_windows=200/200 dwell=40919/40919  (15.3s)
PASS  lineage kafka→iceberg demo-soccer-hero       source=59042 bronze_valid=59043 silver=59042 gold_final_player_windows=2179  (10.3s)
PASS  parity batch=stream demo-soccer-faults       player_windows=2209/2209 team_windows=204/204 dwell=41579/41579  (18.0s)
PASS  lineage kafka→iceberg demo-soccer-faults     source=60282 bronze_valid=62620 silver=60282 gold_final_player_windows=2209  (5.6s)
PASS  parity batch=stream demo-nba                 player_windows=916/916 team_windows=180/180 dwell=34217/34217  (22.5s)
PASS  lineage kafka→iceberg demo-nba               source=79963 bronze_valid=79964 silver=79963 gold_final_player_windows=916  (3.4s)
PASS  fault session counters                       duplicates=1748 corrections=589 quarantined=114  (0.0s)
PASS  hero session clean                           duplicates=0 quarantined=0 late=0 frames=59042  (0.0s)
PASS  analyst eval                                 15/15 passed  (6.7s)
PASS  similar moments lift + change points         hero: lift=1.482 changes=26; faults: lift=1.437 changes=29  (5.3s)
PASS  public demo guard (SMIP_PUBLIC_DEMO=1)       catalog sources=['skillcorner'] nba_meta=404 nba_frames=404 skillcorner_meta=200  (0.6s)
PASS  UI build                                     built in 358ms  (1.9s)
15/15 checks passed
```
<!-- verify:end -->

## What works (verified)

| area | state | evidence |
|---|---|---|
| acquisition | SkillCorner, Metrica, SportVU downloaded at pinned revisions with checksums; StatsBomb and Wyscout downloaded but not normalized | `docs/DATA_SOURCES.md` |
| replay → Kafka → Spark → Iceberg + ClickHouse | three demo sessions end-to-end | `data/demo/seed_report.json` |
| batch/stream parity | exact (0 differences) on hero, faults and NBA sessions | verify block above |
| fault handling | duplicates dropped, corrections applied, malformed records quarantined and attributed by Kafka key; parity still exact | Pipeline view, `docs/FAILURE_SEMANTICS.md` |
| lineage | Kafka offsets → bronze → silver → gold row counts per session | `/api/sessions/{sid}/lineage` |
| similar moments | lift 1.48 / 1.44 over random on the two SkillCorner sessions; the NBA figure is circular and flagged | `docs/MODEL_CARDS/similar-moments-knn.md` |
| shape change points | 26 / 29 / 2 per session, each with evidence | `docs/MODEL_CARDS/shape-change-pelt.md` |
| grounded analyst | 15/15 eval cases, including refusals and the replay-time cutoff | `docs/MODEL_CARDS/grounded-analyst.md` |
| dashboard | live stage (trails, hulls, defensive line, Voronoi, heatmap), timeline, players, pipeline, catalog; public-demo mode | `docs/img/` |
| benchmarks | measured throughput, latency, memory | `docs/BENCHMARKS.md` |
| Airflow (`orchestration` profile) | `smip_quality` DAG run succeeded with `spark-stream` stopped (exact parity 2,179 / 200 / 40,919 rows, lineage ok). `smip_data` is defined but was not triggered during verification | `dags/` |

## Known limitations

- **Single broker, `local[3]` Spark, one Docker VM.** No multi-match concurrency or partition scaling was measured.
- **End-to-end throughput** (unthrottled) is bounded by the stateful engine micro-batches, not by Kafka. See the benchmarks.
- **Paced-replay latency is seconds, not milliseconds** (2 s trigger plus the batch time). That is fine for a replay demo, but it is not a low-latency serving path.
- **Top speed shows provider artefacts.** SkillCorner broadcast tracking includes extrapolated positions, and a few players' max speed reaches 40+ km/h in the players table while staying under the 12.5 m/s implausibility cap. Treat `max_speed_mps` as indicative.
- **NBA:** there is no possession feed ("offense" is a positional heuristic), and sensor time is not the game clock (`docs/CLOCKS.md`).
- **NBA running score** comes from archived NBA.com play-by-play (`sportvu_pbp`, local only), placed by game clock. Free throws show at the start of their stoppage, and events inside tracking gaps show once tracking resumes. Football shows the final score only, because SkillCorner has no goal times.
- **Metrica and NBA are local-only** (license unknown) and hidden with `SMIP_PUBLIC_DEMO=1`.
- **Airflow and the full streaming stack do not fit together** in 7.65 GiB.
- **Iceberg maintenance** (compaction, snapshot expiry) is not automated.

## Removed in v0.1

The Makefile targets `backfill`, `iceberg-maintain` and `train` were removed: they were not wired to working
code. Use `smip batch`, `smip lakehouse inspect` and `smip ml eval` instead.

## Next (out of scope for v0.1)

- StatsBomb 360 and Wyscout adapters (events and freeze frames; already downloaded, not normalized)
- Shot / xG models on event data
- Temporal classifier or learned embeddings for moments
- Qdrant-backed cross-match retrieval (`ai` profile exists, unused)
- `nba_api` joins for play-by-play context (discovered only, restrictive terms)
- Iceberg compaction DAG and snapshot expiry
