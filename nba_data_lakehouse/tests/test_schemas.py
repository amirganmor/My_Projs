"""Tests for table schema definitions."""
from jobs.common.schemas import BRONZE_TABLES, SILVER_TABLES, GOLD_TABLES


def test_bronze_table_count():
    assert len(BRONZE_TABLES) >= 15


def test_silver_table_count():
    assert len(SILVER_TABLES) >= 10


def test_gold_table_count():
    assert len(GOLD_TABLES) >= 10


def test_bronze_names_contain_namespace():
    for name, table in BRONZE_TABLES.items():
        assert table.startswith("nessie.bronze."), f"{name} → {table}"


def test_silver_names_contain_namespace():
    for name, table in SILVER_TABLES.items():
        assert table.startswith("nessie.silver."), f"{name} → {table}"


def test_gold_names_contain_namespace():
    for name, table in GOLD_TABLES.items():
        assert table.startswith("nessie.gold."), f"{name} → {table}"


def test_expected_bronze_tables_exist():
    expected = ["nba_api_players", "advanced_player_metrics", "contracts",
                "mongo_scouting_reports", "shot_chart_zones"]
    for e in expected:
        assert e in BRONZE_TABLES, f"Missing bronze table: {e}"


def test_expected_gold_tables_exist():
    expected = ["scores_underrated_players", "scores_improvement_candidates",
                "scores_trade_targets", "features_value_model"]
    for e in expected:
        assert e in GOLD_TABLES, f"Missing gold table: {e}"
