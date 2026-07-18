"""
Ingest NBA API cached JSON responses into Bronze Iceberg tables.

Source Family 1: Official-style NBA stats (API mock / cached responses)
Tables: bronze.nba_api_players, bronze.nba_api_teams, bronze.nba_api_player_season_stats,
        bronze.nba_api_player_gamelogs, bronze.nba_api_games, bronze.nba_api_standings
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger
from jobs.common.schemas import BRONZE_TABLES
from jobs.common.spark_session import get_spark, stop_spark

log = get_logger("ingest.api")


def _add_metadata(df: DataFrame, source_name: str, batch_id: str) -> DataFrame:
    return (
        df
        .withColumn("ingestion_ts", F.current_timestamp())
        .withColumn("source_name", F.lit(source_name))
        .withColumn("batch_id", F.lit(batch_id))
    )


def _safe_create_df(spark: SparkSession, pdf: pd.DataFrame) -> DataFrame:
    """Create a Spark DataFrame from pandas, handling all-None columns."""
    for col in pdf.columns:
        if pdf[col].isna().all():
            pdf[col] = pdf[col].astype(str)
    return spark.createDataFrame(pdf)


def _create_namespace_if_needed(spark: SparkSession, ns: str) -> None:
    try:
        spark.sql(f"CREATE NAMESPACE IF NOT EXISTS {ns}")
    except Exception:
        pass


def _write_bronze(df: DataFrame, table: str) -> int:
    if df.count() == 0:
        log.warning(f"  Empty dataframe for {table}, skipping write")
        return 0
    df.writeTo(table).using("iceberg").createOrReplace()
    count = df.count()
    log.info(f"  Wrote {count:,} rows to {table}")
    return count


def _load_multi_season_json(
    base_dir: Path,
    data_key: str,
    cast_all_str: bool = False,
) -> pd.DataFrame:
    """Load all per-season JSON files under *base_dir* into one pandas DataFrame.

    Each file is expected to contain {data_key: [rows...]} (or for standings,
    the first list-valued key is used when data_key is None).
    A 'season' column is added from the filename stem.

    pandas.concat auto-aligns columns across seasons so differing schemas
    (e.g. bubble-season extras) are handled gracefully with NaN fills.
    """
    all_frames: list[pd.DataFrame] = []

    for json_file in sorted(base_dir.glob("*.json")):
        season = json_file.stem
        with open(json_file) as f:
            data = json.load(f)

        if data_key:
            rows = data.get(data_key, [])
        else:
            rows = []
            for val in data.values():
                if isinstance(val, list) and val:
                    rows = val
                    break

        if not rows:
            continue

        pdf = pd.DataFrame(rows)
        pdf["season"] = season
        all_frames.append(pdf)
        log.info(f"  Read {season}: {len(pdf):,} rows")

    if not all_frames:
        return pd.DataFrame()

    combined = pd.concat(all_frames, ignore_index=True)

    if cast_all_str:
        combined = combined.astype(str)

    return combined


# ------------------------------------------------------------------
# Individual source ingestors
# ------------------------------------------------------------------

def ingest_players(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    path = cfg.api_mock_path / "commonallplayers.json"
    if not path.exists():
        log.warning("commonallplayers.json not found")
        return 0

    with open(path) as f:
        data = json.load(f)

    players = data.get("CommonAllPlayers", [])
    if not players:
        return 0

    df = _safe_create_df(spark, pd.DataFrame(players))
    df = _add_metadata(df, "nba_api", batch_id)
    return _write_bronze(df, BRONZE_TABLES["nba_api_players"])


def ingest_teams(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    path = cfg.api_mock_path / "teams.json"
    if not path.exists():
        log.warning("teams.json not found")
        return 0

    with open(path) as f:
        teams = json.load(f)

    df = _safe_create_df(spark, pd.DataFrame(teams))
    df = _add_metadata(df, "nba_api", batch_id)
    return _write_bronze(df, BRONZE_TABLES["nba_api_teams"])


def ingest_player_season_stats(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    stats_dir = cfg.api_mock_path / "player_season_stats"
    if not stats_dir.exists():
        return 0

    log.info("Ingesting player season stats...")
    combined = _load_multi_season_json(stats_dir, "LeagueDashPlayerStats")
    if combined.empty:
        return 0

    df = _safe_create_df(spark, combined)
    df = _add_metadata(df, "nba_api", batch_id)
    return _write_bronze(df, BRONZE_TABLES["nba_api_player_season_stats"])


def ingest_player_gamelogs(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    logs_dir = cfg.api_mock_path / "player_gamelogs"
    if not logs_dir.exists():
        return 0

    log.info("Ingesting player game logs...")
    combined = _load_multi_season_json(logs_dir, "PlayerGameLogs")
    if combined.empty:
        return 0

    df = _safe_create_df(spark, combined)
    df = _add_metadata(df, "nba_api", batch_id)
    return _write_bronze(df, BRONZE_TABLES["nba_api_player_gamelogs"])


def ingest_games(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    games_dir = cfg.api_mock_path / "team_game_results"
    if not games_dir.exists():
        return 0

    log.info("Ingesting game results...")
    combined = _load_multi_season_json(games_dir, "LeagueGameFinderResults")
    if combined.empty:
        return 0

    df = _safe_create_df(spark, combined)
    df = _add_metadata(df, "nba_api", batch_id)
    return _write_bronze(df, BRONZE_TABLES["nba_api_games"])


def ingest_standings(spark: SparkSession, batch_id: str) -> int:
    cfg = get_config()
    standings_dir = cfg.api_mock_path / "league_standings"
    if not standings_dir.exists():
        return 0

    log.info("Ingesting standings...")
    combined = _load_multi_season_json(standings_dir, data_key=None, cast_all_str=True)
    if combined.empty:
        return 0

    df = _safe_create_df(spark, combined)
    df = _add_metadata(df, "nba_api", batch_id)
    return _write_bronze(df, BRONZE_TABLES["nba_api_standings"])


# ------------------------------------------------------------------
# Orchestration
# ------------------------------------------------------------------

def run_all() -> dict[str, int]:
    """Ingest all NBA API sources into bronze."""
    spark = get_spark("ingest_nba_api")
    batch_id = f"api_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    _create_namespace_if_needed(spark, "nessie.bronze")

    counts = {}
    try:
        counts["players"] = ingest_players(spark, batch_id)
        counts["teams"] = ingest_teams(spark, batch_id)
        counts["player_season_stats"] = ingest_player_season_stats(spark, batch_id)
        counts["player_gamelogs"] = ingest_player_gamelogs(spark, batch_id)
        counts["games"] = ingest_games(spark, batch_id)
        counts["standings"] = ingest_standings(spark, batch_id)
    finally:
        stop_spark(spark)

    log.info(f"API ingestion complete: {counts}")
    return counts


if __name__ == "__main__":
    run_all()
