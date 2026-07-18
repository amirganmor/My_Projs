-- NBA Source Tables: Contracts, Injuries, Rosters, Teams

CREATE TABLE IF NOT EXISTS teams (
    team_id         VARCHAR(10) PRIMARY KEY,
    team_name       VARCHAR(100) NOT NULL,
    team_abbr       VARCHAR(5) NOT NULL,
    conference      VARCHAR(10),
    division        VARCHAR(20),
    city            VARCHAR(50),
    arena           VARCHAR(100),
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contracts (
    contract_id     SERIAL PRIMARY KEY,
    player_name     VARCHAR(150) NOT NULL,
    team_abbr       VARCHAR(50),
    season          VARCHAR(10) NOT NULL,
    salary          BIGINT NOT NULL,
    years_remaining INTEGER DEFAULT 1,
    guaranteed      BOOLEAN DEFAULT TRUE,
    contract_type   VARCHAR(30) DEFAULT 'standard',
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS injuries (
    injury_id       SERIAL PRIMARY KEY,
    player_name     VARCHAR(150) NOT NULL,
    team_abbr       VARCHAR(50),
    season          VARCHAR(10) NOT NULL,
    injury_type     VARCHAR(100),
    games_missed    INTEGER DEFAULT 0,
    status          VARCHAR(30) DEFAULT 'resolved',
    injury_date     DATE,
    return_date     DATE,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rosters (
    roster_id       SERIAL PRIMARY KEY,
    player_name     VARCHAR(150) NOT NULL,
    team_abbr       VARCHAR(50) NOT NULL,
    season          VARCHAR(10) NOT NULL,
    jersey_number   INTEGER,
    position        VARCHAR(10),
    height          VARCHAR(10),
    weight          INTEGER,
    birth_date      DATE,
    country         VARCHAR(50) DEFAULT 'USA',
    draft_year      INTEGER,
    draft_pick      INTEGER,
    years_pro       INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contracts_player ON contracts(player_name);
CREATE INDEX IF NOT EXISTS idx_contracts_season ON contracts(season);
CREATE INDEX IF NOT EXISTS idx_injuries_player ON injuries(player_name);
CREATE INDEX IF NOT EXISTS idx_injuries_season ON injuries(season);
CREATE INDEX IF NOT EXISTS idx_rosters_player ON rosters(player_name);
CREATE INDEX IF NOT EXISTS idx_rosters_season ON rosters(season);
CREATE INDEX IF NOT EXISTS idx_rosters_team ON rosters(team_abbr);
