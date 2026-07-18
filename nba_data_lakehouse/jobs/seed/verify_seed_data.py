"""Verify all seed data files are present and non-empty."""
from __future__ import annotations

from pathlib import Path

from jobs.common.config import get_config
from jobs.common.logging_utils import get_logger

log = get_logger("seed.verify")

REQUIRED_DIRS = [
    "api_mock/player_season_stats",
    "api_mock/player_gamelogs",
    "api_mock/league_standings",
    "api_mock/team_game_results",
    "files/advanced_metrics",
    "files/historical",
    "files/shot_charts",
    "postgres",
    "mongo",
]

REQUIRED_FILES = [
    "api_mock/commonallplayers.json",
    "api_mock/teams.json",
    "files/historical/historical_player_seasons.csv",
    "files/historical/historical_team_standings.csv",
    "postgres/contracts.csv",
    "postgres/rosters.csv",
    "mongo/player_profiles.json",
    "mongo/scouting_reports.json",
]


def verify_seed_data() -> dict:
    """Check seed directory completeness. Returns summary dict."""
    cfg = get_config()
    seed = cfg.seed_path
    summary = {"ok": True, "missing_files": [], "dir_file_counts": {}}

    for rf in REQUIRED_FILES:
        p = seed / rf
        if not p.exists() or p.stat().st_size < 10:
            summary["missing_files"].append(rf)
            summary["ok"] = False
            log.warning(f"  MISSING: {rf}")

    for d in REQUIRED_DIRS:
        dp = seed / d
        if dp.exists():
            files = [f for f in dp.iterdir() if f.is_file()]
            summary["dir_file_counts"][d] = len(files)
            log.info(f"  {d}: {len(files)} files")
        else:
            summary["dir_file_counts"][d] = 0
            log.warning(f"  DIR MISSING: {d}")

    if summary["ok"]:
        log.info("Seed data verification: ALL OK")
    else:
        log.warning(f"Seed data verification: {len(summary['missing_files'])} files missing")

    return summary
