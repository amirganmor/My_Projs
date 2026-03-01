# Scoreboard Database Schema

**Database:** `scoreboard`
**User:** `scoreboard`
**Port:** `5433` (mapped from container's 5432)

## Data Flow Overview

Soccer producers (Premier League, La Liga, Champions League) extract 20+ statistics fields, team colors, formations, full commentary plays, and detailed lineups from ESPN's `/summary` endpoint. Live games use an 8-second cache TTL for fast data updates; finished games use 30 seconds.

The Kafka message schema includes `stats`, `plays`, and `lineups` arrays alongside the existing `events` and `periods`. The `stats` field contains keys like `possession`, `shots`, `shotsOnTarget`, `shotsBlocked`, `corners`, `fouls`, `passes`, `accuratePasses`, `passAccuracy`, `crosses`, `tackles`, `interceptions`, `clearances`, `longBalls`, `yellowCards`, `redCards`, etc. Lineups include `color`, `altColor`, `formation`, `homeAway`, and players with `positionFull` details.

---

## Tables

### `game_scores`

Stores live game score snapshots ingested from Kafka via PySpark Structured Streaming. A new row is appended each time a score change is detected by any of the 5 sport producers.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `SERIAL` (PK) | NOT NULL | auto-increment | Unique row identifier |
| `league` | `VARCHAR(20)` | NOT NULL | -- | `nba`, `nfl`, `premier_league`, `la_liga`, `champions_league` |
| `game_id` | `VARCHAR(50)` | NOT NULL | -- | Unique game/event ID from the data source |
| `home_team` | `VARCHAR(100)` | NULL | -- | Home team display name |
| `away_team` | `VARCHAR(100)` | NULL | -- | Away team display name |
| `home_score` | `INTEGER` | NULL | -- | Home team score at time of ingestion |
| `away_score` | `INTEGER` | NULL | -- | Away team score at time of ingestion |
| `status_text` | `VARCHAR(100)` | NULL | -- | Game status (e.g. `Final`, `Second Half`, `Q3 5:22`, `Scheduled`) |
| `ingested_at` | `TIMESTAMP` | NULL | `NOW()` | Timestamp when the row was written |

**Indexes:** `idx_game_scores_league (league)`, `idx_game_scores_game_id (game_id)`

---

### `match_events`

Stores match events for soccer games: goals, yellow cards, red cards, and substitutions. Ingested via PySpark from the enhanced Kafka messages.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `SERIAL` (PK) | NOT NULL | auto-increment | Unique row identifier |
| `league` | `VARCHAR(20)` | NOT NULL | -- | League identifier |
| `game_id` | `VARCHAR(50)` | NOT NULL | -- | Game/event ID |
| `event_type` | `VARCHAR(20)` | NOT NULL | -- | `goal`, `yellow_card`, `red_card`, `substitution` |
| `minute` | `INTEGER` | NULL | -- | Minute of the event |
| `player_name` | `VARCHAR(100)` | NULL | -- | Player involved (scorer, carded player) |
| `player_in` | `VARCHAR(100)` | NULL | -- | Substitution: player coming on |
| `player_out` | `VARCHAR(100)` | NULL | -- | Substitution: player coming off |
| `team` | `VARCHAR(100)` | NULL | -- | Team name |
| `ingested_at` | `TIMESTAMP` | NULL | `NOW()` | Timestamp when the row was written |

**Indexes:** `idx_match_events_game (league, game_id)`

---

### `period_scores`

Stores quarter/half scores for all sports. Basketball and football have quarter scores; soccer has half-time scores.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `SERIAL` (PK) | NOT NULL | auto-increment | Unique row identifier |
| `league` | `VARCHAR(20)` | NOT NULL | -- | League identifier |
| `game_id` | `VARCHAR(50)` | NOT NULL | -- | Game/event ID |
| `period_number` | `INTEGER` | NOT NULL | -- | Period number (1, 2, 3, 4 for quarters; 1, 2 for halves) |
| `home_score` | `INTEGER` | NULL | -- | Home team score in this period |
| `away_score` | `INTEGER` | NULL | -- | Away team score in this period |
| `ingested_at` | `TIMESTAMP` | NULL | `NOW()` | Timestamp when the row was written |

**Indexes:** `idx_period_scores_game (league, game_id)`

---

### `player_season_stats`

Stores aggregated season-level player statistics. Updated every 6 hours by the batch fetcher. Uses JSONB for sport-specific stat flexibility.

| Column | Type | Nullable | Default | Description |
|---|---|---|---|---|
| `id` | `SERIAL` (PK) | NOT NULL | auto-increment | Unique row identifier |
| `league` | `VARCHAR(20)` | NOT NULL | -- | League identifier |
| `season` | `VARCHAR(10)` | NOT NULL | -- | Season identifier (e.g. `2025-26`, `2025`) |
| `player_name` | `VARCHAR(100)` | NOT NULL | -- | Player display name |
| `team` | `VARCHAR(100)` | NULL | -- | Team name or abbreviation |
| `games_played` | `INTEGER` | NULL | -- | Number of games played |
| `stats` | `JSONB` | NOT NULL | -- | Sport-specific statistics (see below) |
| `updated_at` | `TIMESTAMP` | NULL | `NOW()` | Last update timestamp |

**Unique constraint:** `(league, season, player_name, team)`
**Indexes:** `idx_player_stats_league (league, season)`

#### JSONB `stats` field examples

**NBA:**
```json
{"points": 28.5, "rebounds": 7.2, "assists": 5.1, "steals": 1.3, "blocks": 0.8, "fg_pct": 0.512, "fg3_pct": 0.381, "ft_pct": 0.887, "minutes": 35.2, "turnovers": 2.8}
```

**NFL:**
```json
{"passingYards": 4707, "category": "passing"}
```

**Soccer:**
```json
{"goals": 15}
```

---

## Example Queries

Latest score for every game:

```sql
SELECT DISTINCT ON (league, game_id)
    league, game_id, home_team, home_score, away_team, away_score, status_text, ingested_at
FROM game_scores
ORDER BY league, game_id, ingested_at DESC;
```

All events for a specific soccer match:

```sql
SELECT event_type, minute, player_name, player_in, player_out, team
FROM match_events
WHERE game_id = '<GAME_ID>'
ORDER BY minute;
```

Quarter scores for an NBA game:

```sql
SELECT period_number, home_score, away_score
FROM period_scores
WHERE league = 'nba' AND game_id = '<GAME_ID>'
ORDER BY period_number;
```

Top NBA scorers this season:

```sql
SELECT player_name, team, games_played,
       (stats->>'points')::numeric AS ppg
FROM player_season_stats
WHERE league = 'nba' AND season = '2025-26'
ORDER BY ppg DESC
LIMIT 20;
```

---

## Connection

```
Host:     localhost (or postgres from within Docker)
Port:     5433 (mapped from container's 5432)
Database: scoreboard
User:     scoreboard
Password: scoreboard
```

```bash
docker exec -it postgres psql -U scoreboard
```
