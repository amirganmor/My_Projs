# Code Reference Guide

Quick-reference companion to `TUTORIAL.md` -- lists the exact files and functions relevant to each section of the video tutorial.

---

## Introduction

| File | Functions / Details |
|------|---------------------|
| `docker-compose.yaml` | All 14 service definitions |
| `scoreboard_ui/templates/index.html` | `renderGames()`, `refresh()` |

---

## Architecture Overview

| File | Functions / Details |
|------|---------------------|
| `docker-compose.yaml` | Service definitions, `depends_on`, `healthcheck` blocks |
| `nba/producer.py` | `start_engine()`, `normalize_games()` |
| `nfl/producer.py` | `start_engine()`, `fetch_games()` |
| `shared/soccer_producer.py` | `SoccerEngine` class, `start()`, `fetch_games()`, `fingerprint()` |
| `premier_league/producer.py` | Thin wrapper -> `SoccerEngine(kafka_topic="premier_league_scores", ...)` |
| `la_liga/producer.py` | Thin wrapper -> `SoccerEngine(kafka_topic="la_liga_scores", ...)` |
| `champions_league/producer.py` | Thin wrapper -> `SoccerEngine(kafka_topic="champions_league_scores", ...)` |
| `scoreboard_ui/app.py` | `kafka_listener()`, `api_scores()` |
| `spark_analytics/stream_to_postgres.py` | `write_batch()` |
| `player_stats/fetch_stats.py` | `run_fetch_cycle()` |

---

## Data Sources Deep Dive

| File | Functions / Details |
|------|---------------------|
| `shared/soccer_producer.py` | `fetch_match_details()`, `_parse_stats()`, `_parse_commentary()`, `_parse_lineups()`, `_summary_ttl()` |
| `shared/soccer_producer.py` | Constants: `SUMMARY_TTL_LIVE` (3s), `SUMMARY_TTL_DEFAULT` (30s), `MAX_FETCH_WORKERS` (6), `STAT_MAP` |
| `nba/producer.py` | `fetch_espn_game_map()`, `fetch_espn_plays()`, `_find_espn_coord()`, `fetch_boxscore()` |
| `nba/producer.py` | Constants: `PBP_TTL` (5s), `BS_TTL` (10s), `ESPN_MAP_TTL` (60s), `ESPN_PLAYS_TTL` (5s) |
| `nfl/producer.py` | `fetch_match_details()`, `_summary_ttl()`, `_extract_drive()`, `_extract_play()` |
| `nfl/producer.py` | Constants: `SUMMARY_TTL_LIVE` (5s), `SUMMARY_TTL_DEFAULT` (30s), `MAX_FETCH_WORKERS` (6) |

---

## Demo: Starting the Platform

| File | Functions / Details |
|------|---------------------|
| `docker-compose.yaml` | All service definitions, `depends_on`, `healthcheck` blocks |
| `nba/Dockerfile` | Build steps, `COPY`, `CMD ["python", "producer.py"]` |
| `nfl/Dockerfile` | Build steps, `COPY`, `CMD ["python", "producer.py"]` |
| `premier_league/Dockerfile` | Build steps, `COPY shared/`, `CMD ["python", "producer.py"]` |
| `la_liga/Dockerfile` | Same pattern as `premier_league` |
| `champions_league/Dockerfile` | Same pattern as `premier_league` |
| `nba/producer.py` | `start_engine()` -- main loop entry point |
| `shared/soccer_producer.py` | `SoccerEngine.start()` -- main loop entry point |
| `nfl/producer.py` | `start_engine()` -- main loop entry point |

---

## Demo: Live Scoreboard UI

| File | Functions / Details |
|------|---------------------|
| `scoreboard_ui/app.py` | `kafka_listener()` -- background Kafka consumer thread |
| `scoreboard_ui/app.py` | `api_scores()` -- GET `/api/scores` returns in-memory dict |
| `scoreboard_ui/templates/index.html` | `refresh()` -- fetches `/api/scores` every 3 seconds |
| `scoreboard_ui/templates/index.html` | `renderGames()` -- renders league sections, CDC fingerprint diffing |
| `scoreboard_ui/templates/index.html` | `renderGameRow()` -- single match row with score, status |
| `scoreboard_ui/templates/index.html` | `toggleDetail()` -- expand/collapse match detail panel |
| `scoreboard_ui/templates/index.html` | `switchTab()` -- tab switching (Live / Stats / Line-ups / Box Score) |
| `scoreboard_ui/templates/index.html` | `renderStats()` -- 20+ stat comparison bars (soccer, NBA, NFL) |
| `scoreboard_ui/templates/index.html` | `renderLineups()` -- formation, players, substitution tracking |
| `scoreboard_ui/templates/index.html` | `renderNBABoxScore()` -- full player stats table (starters + bench + totals) |
| `scoreboard_ui/templates/index.html` | `renderNFLDrives()` -- drive summaries with yard progression |
| `scoreboard_ui/templates/index.html` | `renderNFLScoringPlays()` -- scoring plays by quarter |
| `scoreboard_ui/templates/index.html` | `renderPeriodTable()` -- quarter/half score table |
| `scoreboard_ui/templates/index.html` | `rowFingerprint()`, `detailFingerprint()` -- two-tier CDC fingerprinting |

---

## Demo: Live Match Tracker

| File | Functions / Details |
|------|---------------------|
| `scoreboard_ui/templates/index.html` | `BallCtrl` object -- persistent ball controller |
| `scoreboard_ui/templates/index.html` | `BallCtrl.setTarget()` -- queue new ball position |
| `scoreboard_ui/templates/index.html` | `BallCtrl.inject()`, `BallCtrl.injectAll()` -- create/attach ball DOM element |
| `scoreboard_ui/templates/index.html` | `BallCtrl._animateQueue()` -- step through queued positions |
| `scoreboard_ui/templates/index.html` | `BallCtrl._bezierPoints()` -- generate curved interpolation waypoints |
| `scoreboard_ui/templates/index.html` | `BallCtrl._idleDrift()` -- subtle micro-movement when no new data |
| `scoreboard_ui/templates/index.html` | `svgSoccerPitch(g, gameKey)` -- SVG pitch rendering, play coordinate extraction |
| `scoreboard_ui/templates/index.html` | `playToCoord()` -- dead-ball position overrides (corner, goal kick, penalty, kickoff) |
| `scoreboard_ui/templates/index.html` | `estimatePositionFromText()` -- text-based position inference |
| `scoreboard_ui/templates/index.html` | `_hashCode()`, `_pseudoRand()` -- deterministic position hashing |
| `scoreboard_ui/templates/index.html` | `svgBasketballCourt(g, gameKey)` -- NBA court SVG |
| `scoreboard_ui/templates/index.html` | `nbaToCourtPct()` -- maps nba_api shot coordinates to SVG |
| `scoreboard_ui/templates/index.html` | `espnNbaToCourtPct()` -- maps ESPN coordinate.x/y to SVG |
| `scoreboard_ui/templates/index.html` | `nbaFallbackPct()` -- fallback position when no coordinates |
| `scoreboard_ui/templates/index.html` | `svgFootballField(g, gameKey)` -- NFL field SVG |
| `scoreboard_ui/templates/index.html` | `yardToX()` -- converts yardsToEndzone to SVG x-position |
| `scoreboard_ui/templates/index.html` | `renderTimeline()` -- event timeline strip below pitch |
| `scoreboard_ui/templates/index.html` | `renderSoccerPlays()` -- live commentary feed with emoji event icons |

---

## Code Walkthrough

| File | Functions / Details |
|------|---------------------|
| `shared/soccer_producer.py` | `SoccerEngine` class -- all methods |
| `shared/soccer_producer.py` | `fetch_games()` -- fetches ESPN scoreboard + parallel summary calls |
| `shared/soccer_producer.py` | `fetch_match_details()` -- parses events, stats, commentary, lineups |
| `shared/soccer_producer.py` | `fingerprint()` -- change detection for Kafka dedup |
| `shared/soccer_producer.py` | `display()` -- console output for Docker logs |
| `premier_league/producer.py` | 12-line wrapper: `SoccerEngine(kafka_topic=..., league_key=..., espn_slug=..., display_name=...).start()` |
| `la_liga/producer.py` | Same thin wrapper pattern |
| `champions_league/producer.py` | Same thin wrapper pattern |
| `scoreboard_ui/app.py` | `kafka_listener()` -- retry loop with exponential backoff (3s -> 30s) |
| `scoreboard_ui/app.py` | `api_scores()` -- returns in-memory scores dict as JSON |
| `scoreboard_ui/app.py` | `VALID_LEAGUES` -- allowlist for message validation |
| `spark_analytics/stream_to_postgres.py` | `write_batch(batch_df, batch_id)` -- foreachBatch callback |
| `spark_analytics/stream_to_postgres.py` | `pg_write(df, table, mode)` -- JDBC write to PostgreSQL |

---

## Database and Analytics

| File | Functions / Details |
|------|---------------------|
| `init.sql` | `game_scores` table -- append-only score snapshots with `UNIQUE(league, game_id, home_score, away_score, status_text)` |
| `init.sql` | `match_events` table -- goals, cards, substitutions (soccer) |
| `init.sql` | `period_scores` table -- quarter/half score breakdowns |
| `init.sql` | `player_season_stats` table -- JSONB stats with `UNIQUE(league, season, player_name, team)` |
| `init.sql` | Indexes: `idx_game_scores_league`, `idx_game_scores_game_id`, `idx_match_events_game`, `idx_period_scores_game`, `idx_player_stats_league` |
| `spark_analytics/stream_to_postgres.py` | `write_batch()` -- `explode()` + JDBC write to 3 tables |
| `spark_analytics/stream_to_postgres.py` | `pg_write()` -- reusable JDBC writer |
| `player_stats/fetch_stats.py` | `get_conn()` -- PostgreSQL connection via psycopg2 |
| `player_stats/fetch_stats.py` | `upsert_stats()` -- `ON CONFLICT` upsert for player stats |
| `player_stats/fetch_stats.py` | `fetch_nba_stats()` -- nba_api `leaguedashplayerstats` |
| `player_stats/fetch_stats.py` | `fetch_espn_football_stats()` -- ESPN NFL leaders |
| `player_stats/fetch_stats.py` | `fetch_espn_soccer_stats()` -- ESPN soccer leaders |
| `player_stats/fetch_stats.py` | `run_fetch_cycle()` -- orchestrates all fetches, runs every 6h |
| `DATABASE_SCHEMA.md` | Full column definitions and example queries |

---

## Engineering Practices

| File | Functions / Details |
|------|---------------------|
| `shared/soccer_producer.py` | `logging.basicConfig(...)` -- structured logging with timestamps |
| `shared/soccer_producer.py` | Docstrings on all public methods |
| `shared/soccer_producer.py` | Named constants: `SUMMARY_TTL_LIVE`, `SUMMARY_TTL_DEFAULT`, `MAX_FETCH_WORKERS`, `SKIP_STATUSES`, `LIVE_STATUSES` |
| `nba/producer.py` | Named constants: `RECENT_PLAYS_LIMIT`, `MAX_CLOCK_DISTANCE`, `CLOCK_MATCH_TOLERANCE`, `ESPN_COORD_ABS_LIMIT` |
| `nfl/producer.py` | Named constants: `MAX_DRIVES`, `MAX_PLAYS`, `SUMMARY_TTL_DEFAULT`, `SUMMARY_TTL_LIVE`, `MAX_FETCH_WORKERS` |
| `scoreboard_ui/templates/index.html` | `escapeHtml()` -- XSS prevention, applied to 40+ dynamic insertions |
| `scoreboard_ui/app.py` | `VALID_LEAGUES` allowlist -- validates Kafka message `league` field |
| `scoreboard_ui/app.py` | `kafka_listener()` -- `while True` retry with exponential backoff, `metadata_max_age_ms=10000`, `reconnect_backoff_ms=500` |
| All `requirements.txt` (8 files) | Version range pins (`>=x,<y`) for reproducible builds |
| `docker-compose.yaml` | Pinned images: `apache/kafka:3.7.0`, `provectuslabs/kafka-ui:v0.7.2`, `postgres:16`, `apache/spark:3.5.0` |
| `docker-compose.yaml` | `spark_checkpoint` named volume for streaming state persistence |
| `init.sql` | `UNIQUE` constraints on `game_scores` and `player_season_stats` |

---

## Production Path & Future Work

| File | Functions / Details |
|------|---------------------|
| `scoreboard_ui/templates/index.html` | `BallCtrl.setTarget()` -- architecture ready for real x,y coordinate feeds |
| `scoreboard_ui/app.py` | `kafka_listener()` -- where WebSocket/SSE would replace HTTP polling |
| `docker-compose.yaml` | Where Redis and Grafana services would be added |
| `init.sql` | `game_scores` table -- time series data for ML win probability models |
| `PRESENTATION.md` | Slide 11 -- Production Scaling & Future Work |

---

## Closing -- Full Project Map

| Component | Files |
|-----------|-------|
| **NBA Producer** | `nba/producer.py`, `nba/Dockerfile`, `nba/requirements.txt`, `nba/samples/` |
| **NFL Producer** | `nfl/producer.py`, `nfl/Dockerfile`, `nfl/requirements.txt`, `nfl/samples/` |
| **Soccer Engine** | `shared/soccer_producer.py`, `shared/__init__.py` |
| **Premier League** | `premier_league/producer.py`, `premier_league/Dockerfile`, `premier_league/requirements.txt`, `premier_league/samples/` |
| **La Liga** | `la_liga/producer.py`, `la_liga/Dockerfile`, `la_liga/requirements.txt`, `la_liga/samples/` |
| **Champions League** | `champions_league/producer.py`, `champions_league/Dockerfile`, `champions_league/requirements.txt`, `champions_league/samples/` |
| **Scoreboard UI** | `scoreboard_ui/app.py`, `scoreboard_ui/templates/index.html`, `scoreboard_ui/Dockerfile`, `scoreboard_ui/requirements.txt` |
| **Spark Streaming** | `spark_analytics/stream_to_postgres.py`, `spark_analytics/Dockerfile`, `spark_analytics/requirements.txt` |
| **Player Stats Batch** | `player_stats/fetch_stats.py`, `player_stats/Dockerfile`, `player_stats/requirements.txt` |
| **Infrastructure** | `docker-compose.yaml`, `init.sql` |
| **Documentation** | `README.md`, `PRESENTATION.md`, `TUTORIAL.md`, `DATABASE_SCHEMA.md`, `CODE_REFERENCE.md` |
| **GitHub** | `github.com/dreamgroup-il/nba-proj` |
