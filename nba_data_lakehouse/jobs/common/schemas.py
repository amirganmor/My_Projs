"""
Iceberg table schemas and namespace definitions for bronze / silver / gold layers.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------

BRONZE_NS = "nessie.bronze"
SILVER_NS = "nessie.silver"
GOLD_NS = "nessie.gold"

NAMESPACES = [BRONZE_NS, SILVER_NS, GOLD_NS]

# ---------------------------------------------------------------------------
# Bronze table names  (source-shaped raw data)
# ---------------------------------------------------------------------------

BRONZE_TABLES = {
    # Source 1: NBA API official stats
    "nba_api_players": f"{BRONZE_NS}.nba_api_players",
    "nba_api_teams": f"{BRONZE_NS}.nba_api_teams",
    "nba_api_player_season_stats": f"{BRONZE_NS}.nba_api_player_season_stats",
    "nba_api_player_gamelogs": f"{BRONZE_NS}.nba_api_player_gamelogs",
    "nba_api_games": f"{BRONZE_NS}.nba_api_games",
    "nba_api_standings": f"{BRONZE_NS}.nba_api_standings",
    # Source 2: Advanced metrics
    "advanced_player_metrics": f"{BRONZE_NS}.advanced_player_metrics",
    # Source 3: Historical bulk
    "historical_player_seasons": f"{BRONZE_NS}.historical_player_seasons",
    "historical_box_scores": f"{BRONZE_NS}.historical_box_scores",
    "historical_team_standings": f"{BRONZE_NS}.historical_team_standings",
    # Source 4: Shot charts
    "shot_chart_zones": f"{BRONZE_NS}.shot_chart_zones",
    "shot_chart_details": f"{BRONZE_NS}.shot_chart_details",
    # Source 5: Postgres (contracts / injuries / rosters)
    "contracts": f"{BRONZE_NS}.contracts",
    "injuries": f"{BRONZE_NS}.injuries",
    "rosters": f"{BRONZE_NS}.rosters",
    # Source 6: MongoDB (scouting / profiles)
    "mongo_player_profiles": f"{BRONZE_NS}.mongo_player_profiles",
    "mongo_scouting_reports": f"{BRONZE_NS}.mongo_scouting_reports",
}

# ---------------------------------------------------------------------------
# Silver table names  (conformed dimensions and facts)
# ---------------------------------------------------------------------------

SILVER_TABLES = {
    "dim_players": f"{SILVER_NS}.dim_players",
    "dim_teams": f"{SILVER_NS}.dim_teams",
    "dim_seasons": f"{SILVER_NS}.dim_seasons",
    "dim_games": f"{SILVER_NS}.dim_games",
    "fact_player_game_stats": f"{SILVER_NS}.fact_player_game_stats",
    "fact_player_season_stats": f"{SILVER_NS}.fact_player_season_stats",
    "fact_player_contracts": f"{SILVER_NS}.fact_player_contracts",
    "fact_player_injuries": f"{SILVER_NS}.fact_player_injuries",
    "fact_player_profiles": f"{SILVER_NS}.fact_player_profiles",
    "fact_team_results": f"{SILVER_NS}.fact_team_results",
    "fact_player_shot_profiles": f"{SILVER_NS}.fact_player_shot_profiles",
    "player_source_mapping": f"{SILVER_NS}.player_source_mapping",
}

# ---------------------------------------------------------------------------
# Gold table names  (analytics marts, features, scores)
# ---------------------------------------------------------------------------

GOLD_TABLES = {
    # Analytics marts
    "player_season_summary": f"{GOLD_NS}.player_season_summary",
    "player_value_vs_salary": f"{GOLD_NS}.player_value_vs_salary",
    "player_improvement_summary": f"{GOLD_NS}.player_improvement_summary",
    "trade_target_candidates": f"{GOLD_NS}.trade_target_candidates",
    "source_coverage_summary": f"{GOLD_NS}.source_coverage_summary",
    "data_quality_summary": f"{GOLD_NS}.data_quality_summary",
    # ML feature tables
    "features_value_model": f"{GOLD_NS}.features_value_model",
    "features_improvement_model": f"{GOLD_NS}.features_improvement_model",
    "features_trade_target_model": f"{GOLD_NS}.features_trade_target_model",
    # Scored outputs
    "scores_underrated_players": f"{GOLD_NS}.scores_underrated_players",
    "scores_improvement_candidates": f"{GOLD_NS}.scores_improvement_candidates",
    "scores_trade_targets": f"{GOLD_NS}.scores_trade_targets",
}
