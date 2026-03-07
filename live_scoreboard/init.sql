CREATE TABLE IF NOT EXISTS game_scores (
    id SERIAL PRIMARY KEY,
    league VARCHAR(20) NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    home_team VARCHAR(100),
    away_team VARCHAR(100),
    home_score INTEGER,
    away_score INTEGER,
    status_text VARCHAR(100),
    ingested_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(league, game_id, home_score, away_score, status_text)
);

CREATE INDEX IF NOT EXISTS idx_game_scores_league ON game_scores (league);
CREATE INDEX IF NOT EXISTS idx_game_scores_game_id ON game_scores (game_id);

CREATE TABLE IF NOT EXISTS match_events (
    id SERIAL PRIMARY KEY,
    league VARCHAR(20) NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(20) NOT NULL,
    minute INTEGER,
    player_name VARCHAR(100),
    player_in VARCHAR(100),
    player_out VARCHAR(100),
    team VARCHAR(100),
    ingested_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_match_events_game ON match_events (league, game_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_match_events_unique
    ON match_events (league, game_id, event_type,
                     COALESCE(minute, -1),
                     COALESCE(player_name, ''),
                     COALESCE(player_out, ''),
                     team);

CREATE TABLE IF NOT EXISTS period_scores (
    id SERIAL PRIMARY KEY,
    league VARCHAR(20) NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    period_number INTEGER NOT NULL,
    home_score INTEGER,
    away_score INTEGER,
    ingested_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_period_scores_game ON period_scores (league, game_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_period_scores_unique
    ON period_scores (league, game_id, period_number, home_score, away_score);

CREATE TABLE IF NOT EXISTS player_season_stats (
    id SERIAL PRIMARY KEY,
    league VARCHAR(20) NOT NULL,
    season VARCHAR(10) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    team VARCHAR(100),
    games_played INTEGER,
    stats JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(league, season, player_name, team)
);

CREATE INDEX IF NOT EXISTS idx_player_stats_league ON player_season_stats (league, season);
