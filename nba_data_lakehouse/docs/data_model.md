# Data Model

## Source-to-Table Mapping

### Source 1: NBA API Official Stats
| Source File | Bronze Table |
|-------------|-------------|
| commonallplayers.json | bronze.nba_api_players |
| teams.json | bronze.nba_api_teams |
| player_season_stats/*.json | bronze.nba_api_player_season_stats |
| player_gamelogs/*.json | bronze.nba_api_player_gamelogs |
| team_game_results/*.json | bronze.nba_api_games |
| league_standings/*.json | bronze.nba_api_standings |

### Source 2: Advanced Metrics
| Source File | Bronze Table |
|-------------|-------------|
| advanced_stats_*.csv | bronze.advanced_player_metrics |

### Source 3: Historical Bulk
| Source File | Bronze Table |
|-------------|-------------|
| historical_player_seasons.csv | bronze.historical_player_seasons |
| historical_box_scores.csv | bronze.historical_box_scores |
| historical_team_standings.csv | bronze.historical_team_standings |

### Source 4: Shot Charts
| Source File | Bronze Table |
|-------------|-------------|
| shot_zones_*.csv | bronze.shot_chart_zones |
| shot_detail_*.json | bronze.shot_chart_details |

### Source 5: PostgreSQL (Contracts/Injuries/Rosters)
| Source Table | Bronze Table |
|-------------|-------------|
| contracts | bronze.contracts |
| injuries | bronze.injuries |
| rosters | bronze.rosters |

### Source 6: MongoDB (Scouting/Profiles)
| Source Collection | Bronze Table |
|------------------|-------------|
| player_profiles | bronze.mongo_player_profiles |
| scouting_reports | bronze.mongo_scouting_reports |

## Silver Layer (Conformed)

| Table | Grain | Key Sources |
|-------|-------|-------------|
| dim_players | player | API players + rosters |
| dim_teams | team | API teams |
| dim_seasons | season | derived from stats |
| fact_player_season_stats | player × season | API stats + advanced metrics |
| fact_player_game_stats | player × game | API game logs |
| fact_player_contracts | player × season | PostgreSQL contracts |
| fact_player_injuries | player × injury event | PostgreSQL injuries |
| fact_player_shot_profiles | player × season × zone | shot chart zones |
| fact_team_results | team × season | API standings |
| fact_player_profiles | player × season | MongoDB profiles |
| player_source_mapping | player × source | cross-source tracking |

## Gold Layer

| Table | Purpose |
|-------|---------|
| player_season_summary | Comprehensive player-season analytics mart |
| features_value_model | ML features for salary prediction |
| features_improvement_model | ML features for breakout prediction |
| features_trade_target_model | Features for trade target scoring |
| scores_underrated_players | Ranked undervalued players |
| scores_improvement_candidates | Ranked breakout candidates |
| scores_trade_targets | Ranked trade targets |
| source_coverage_summary | Per-source player coverage |
| data_quality_summary | Table health across all layers |
