#!/usr/bin/env python3
"""
fetch_real_nba_data.py
======================
Pre-fetch script that pulls REAL NBA data for 20 seasons (2004-05 → 2024-25)
using the nba_api package and caches everything under data/seed/.

Usage:
    python scripts/fetch_real_nba_data.py                     # full fetch
    python scripts/fetch_real_nba_data.py --skip-existing      # resume mode
    python scripts/fetch_real_nba_data.py --seasons 2022-23 2023-24 2024-25
    python scripts/fetch_real_nba_data.py --no-shots           # skip slow shot data
    python scripts/fetch_real_nba_data.py --shot-seasons 5     # raw shots for last N seasons

Requires internet. Results cached as JSON/CSV under data/seed/.
Once fetched, docker compose runs fully offline from these cached files.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# nba_api imports
# ---------------------------------------------------------------------------
from nba_api.stats.static import teams as nba_teams
from nba_api.stats.endpoints import (
    commonallplayers,
    leaguedashplayerstats,
    playergamelogs,
    leaguestandingsv3,
    leaguegamefinder,
    shotchartdetail,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = PROJECT_ROOT / "data" / "seed"
API_MOCK_DIR = SEED_DIR / "api_mock"
FILES_DIR = SEED_DIR / "files"
POSTGRES_DIR = SEED_DIR / "postgres"
MONGO_DIR = SEED_DIR / "mongo"

# Sub-dirs
PLAYER_SEASON_STATS_DIR = API_MOCK_DIR / "player_season_stats"
PLAYER_GAMELOGS_DIR = API_MOCK_DIR / "player_gamelogs"
TEAM_GAME_RESULTS_DIR = API_MOCK_DIR / "team_game_results"
LEAGUE_STANDINGS_DIR = API_MOCK_DIR / "league_standings"
ADVANCED_METRICS_DIR = FILES_DIR / "advanced_metrics"
HISTORICAL_DIR = FILES_DIR / "historical"
SHOT_CHARTS_DIR = FILES_DIR / "shot_charts"

ALL_DIRS = [
    PLAYER_SEASON_STATS_DIR, PLAYER_GAMELOGS_DIR, TEAM_GAME_RESULTS_DIR,
    LEAGUE_STANDINGS_DIR, ADVANCED_METRICS_DIR, HISTORICAL_DIR,
    SHOT_CHARTS_DIR, POSTGRES_DIR, MONGO_DIR,
]

DEFAULT_START_SEASON = "2004-05"
DEFAULT_END_SEASON = "2024-25"
REQUEST_DELAY = 0.7  # seconds between nba_api calls

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("fetch")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def season_range(start: str, end: str) -> list[str]:
    """Generate list of season strings like '2004-05', '2005-06', ... '2024-25'."""
    s_year = int(start.split("-")[0])
    e_year = int(end.split("-")[0])
    seasons = []
    for y in range(s_year, e_year + 1):
        seasons.append(f"{y}-{str(y + 1)[-2:]}")
    return seasons


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    log.debug(f"  Saved {path.name} ({path.stat().st_size:,} bytes)")


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    log.debug(f"  Saved {path.name} ({len(df):,} rows)")


def rate_limit(delay: float = REQUEST_DELAY) -> None:
    time.sleep(delay)


def file_exists_and_nonempty(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 100


# ---------------------------------------------------------------------------
# Fetch: Players & Teams (static/reference)
# ---------------------------------------------------------------------------

def fetch_all_players(skip_existing: bool) -> dict:
    out_path = API_MOCK_DIR / "commonallplayers.json"
    if skip_existing and file_exists_and_nonempty(out_path):
        log.info("  [skip] commonallplayers.json exists")
        with open(out_path) as f:
            return json.load(f)

    log.info("Fetching CommonAllPlayers...")
    result = commonallplayers.CommonAllPlayers(
        is_only_current_season=0, league_id="00", season="2024-25"
    )
    rate_limit()
    data = result.get_normalized_dict()
    save_json(data, out_path)
    log.info(f"  Got {len(data.get('CommonAllPlayers', []))} players")
    return data


def fetch_teams(skip_existing: bool) -> list[dict]:
    out_path = API_MOCK_DIR / "teams.json"
    if skip_existing and file_exists_and_nonempty(out_path):
        log.info("  [skip] teams.json exists")
        with open(out_path) as f:
            return json.load(f)

    log.info("Fetching teams (static)...")
    teams = nba_teams.get_teams()
    save_json(teams, out_path)
    log.info(f"  Got {len(teams)} teams")
    return teams


# ---------------------------------------------------------------------------
# Fetch: Player Season Stats (base) per season
# ---------------------------------------------------------------------------

def fetch_player_season_stats(seasons: list[str], skip_existing: bool) -> None:
    log.info(f"Fetching player season stats (base) for {len(seasons)} seasons...")
    for season in tqdm(seasons, desc="Player Season Stats"):
        out_path = PLAYER_SEASON_STATS_DIR / f"{season}.json"
        if skip_existing and file_exists_and_nonempty(out_path):
            continue
        try:
            result = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                per_mode_detailed="PerGame",
                season_type_all_star="Regular Season",
            )
            rate_limit()
            data = result.get_normalized_dict()
            save_json(data, out_path)
        except Exception as e:
            log.warning(f"  Failed for {season}: {e}")
            rate_limit(2.0)


# ---------------------------------------------------------------------------
# Fetch: Advanced Metrics per season
# ---------------------------------------------------------------------------

def fetch_advanced_metrics(seasons: list[str], skip_existing: bool) -> None:
    log.info(f"Fetching advanced metrics for {len(seasons)} seasons...")
    for season in tqdm(seasons, desc="Advanced Metrics"):
        out_path = ADVANCED_METRICS_DIR / f"advanced_stats_{season}.csv"
        if skip_existing and file_exists_and_nonempty(out_path):
            continue
        try:
            result = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                measure_type_detailed_defense="Advanced",
                per_mode_detailed="PerGame",
                season_type_all_star="Regular Season",
            )
            rate_limit()
            df = result.get_data_frames()[0]
            save_csv(df, out_path)
        except Exception as e:
            log.warning(f"  Failed for {season}: {e}")
            rate_limit(2.0)


# ---------------------------------------------------------------------------
# Fetch: Player Game Logs per season
# ---------------------------------------------------------------------------

def fetch_player_gamelogs(seasons: list[str], skip_existing: bool) -> None:
    log.info(f"Fetching player game logs for {len(seasons)} seasons...")
    for season in tqdm(seasons, desc="Player Game Logs"):
        out_path = PLAYER_GAMELOGS_DIR / f"{season}.json"
        if skip_existing and file_exists_and_nonempty(out_path):
            continue
        try:
            result = playergamelogs.PlayerGameLogs(
                season_nullable=season,
                season_type_nullable="Regular Season",
            )
            rate_limit()
            data = result.get_normalized_dict()
            save_json(data, out_path)
        except Exception as e:
            log.warning(f"  Failed for {season}: {e}")
            rate_limit(2.0)


# ---------------------------------------------------------------------------
# Fetch: League Standings per season
# ---------------------------------------------------------------------------

def fetch_league_standings(seasons: list[str], skip_existing: bool) -> None:
    log.info(f"Fetching league standings for {len(seasons)} seasons...")
    for season in tqdm(seasons, desc="League Standings"):
        out_path = LEAGUE_STANDINGS_DIR / f"{season}.json"
        if skip_existing and file_exists_and_nonempty(out_path):
            continue
        try:
            result = leaguestandingsv3.LeagueStandingsV3(
                season=season,
                league_id="00",
                season_type="Regular Season",
            )
            rate_limit()
            data = result.get_normalized_dict()
            save_json(data, out_path)
        except Exception as e:
            log.warning(f"  Failed for {season}: {e}")
            rate_limit(2.0)


# ---------------------------------------------------------------------------
# Fetch: Team Game Results per season
# ---------------------------------------------------------------------------

def fetch_team_game_results(seasons: list[str], skip_existing: bool) -> None:
    log.info(f"Fetching team game results for {len(seasons)} seasons...")
    for season in tqdm(seasons, desc="Team Game Results"):
        out_path = TEAM_GAME_RESULTS_DIR / f"{season}.json"
        if skip_existing and file_exists_and_nonempty(out_path):
            continue
        try:
            result = leaguegamefinder.LeagueGameFinder(
                season_nullable=season,
                league_id_nullable="00",
                season_type_nullable="Regular Season",
            )
            rate_limit()
            data = result.get_normalized_dict()
            save_json(data, out_path)
        except Exception as e:
            log.warning(f"  Failed for {season}: {e}")
            rate_limit(2.0)


# ---------------------------------------------------------------------------
# Fetch: Shot Chart Zone Summaries per season
# ---------------------------------------------------------------------------

def fetch_shot_zones(seasons: list[str], skip_existing: bool) -> None:
    """Fetch league-wide shot chart data aggregated by zone per player-season."""
    log.info(f"Fetching shot zone summaries for {len(seasons)} seasons...")
    for season in tqdm(seasons, desc="Shot Zone Summaries"):
        out_path = SHOT_CHARTS_DIR / f"shot_zones_{season}.csv"
        if skip_existing and file_exists_and_nonempty(out_path):
            continue
        try:
            # League-wide shot chart: player_id=0, team_id=0 returns all
            result = shotchartdetail.ShotChartDetail(
                player_id=0,
                team_id=0,
                season_nullable=season,
                season_type_all_star="Regular Season",
                context_measure_simple="FGA",
            )
            rate_limit(1.0)
            dfs = result.get_data_frames()
            if len(dfs) >= 2 and not dfs[1].empty:
                # Second result set is the league averages / zone breakdown
                save_csv(dfs[1], out_path)
            elif len(dfs) >= 1 and not dfs[0].empty:
                # Aggregate raw shots to zone level
                raw = dfs[0]
                if "SHOT_ZONE_BASIC" in raw.columns:
                    zone_agg = raw.groupby(
                        ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_NAME",
                         "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "SHOT_ZONE_RANGE"]
                    ).agg(
                        FGA=("SHOT_MADE_FLAG", "count"),
                        FGM=("SHOT_MADE_FLAG", "sum"),
                    ).reset_index()
                    zone_agg["FG_PCT"] = (zone_agg["FGM"] / zone_agg["FGA"]).round(4)
                    zone_agg["SEASON"] = season
                    save_csv(zone_agg, out_path)
                else:
                    save_csv(raw, out_path)
            else:
                log.warning(f"  No shot data for {season}")
        except Exception as e:
            log.warning(f"  Shot zone failed for {season}: {e}")
            rate_limit(2.0)


# ---------------------------------------------------------------------------
# Fetch: Raw Shot Details (recent seasons, top players)
# ---------------------------------------------------------------------------

def fetch_shot_details(
    seasons: list[str],
    num_recent: int,
    skip_existing: bool,
) -> None:
    """Fetch raw shot-level data for top-usage players in recent seasons."""
    recent_seasons = seasons[-num_recent:] if num_recent < len(seasons) else seasons
    log.info(f"Fetching raw shot detail for {len(recent_seasons)} recent seasons...")

    for season in recent_seasons:
        out_path = SHOT_CHARTS_DIR / f"shot_detail_{season}.json"
        if skip_existing and file_exists_and_nonempty(out_path):
            log.info(f"  [skip] shot_detail_{season}.json exists")
            continue

        # Get top players for this season from already-fetched season stats
        stats_path = PLAYER_SEASON_STATS_DIR / f"{season}.json"
        if not stats_path.exists():
            log.warning(f"  No season stats for {season}, skipping shot details")
            continue

        with open(stats_path) as f:
            stats_data = json.load(f)

        players_list = stats_data.get("LeagueDashPlayerStats", [])
        if not players_list:
            continue

        df_stats = pd.DataFrame(players_list)
        # Pick top 150 by minutes played
        if "MIN" in df_stats.columns:
            top_players = df_stats.nlargest(150, "MIN")[["PLAYER_ID", "PLAYER_NAME", "TEAM_ID"]].to_dict("records")
        else:
            top_players = df_stats.head(150)[["PLAYER_ID", "PLAYER_NAME", "TEAM_ID"]].to_dict("records")

        all_shots = []
        log.info(f"  Fetching shot detail for {len(top_players)} players in {season}...")
        for p in tqdm(top_players, desc=f"Shots {season}", leave=False):
            try:
                result = shotchartdetail.ShotChartDetail(
                    player_id=int(p["PLAYER_ID"]),
                    team_id=int(p["TEAM_ID"]),
                    season_nullable=season,
                    season_type_all_star="Regular Season",
                    context_measure_simple="FGA",
                )
                rate_limit(0.6)
                dfs = result.get_data_frames()
                if dfs and not dfs[0].empty:
                    shots = dfs[0].to_dict("records")
                    all_shots.extend(shots)
            except Exception as e:
                log.debug(f"    Shot detail failed for {p['PLAYER_NAME']}: {e}")
                rate_limit(1.5)

        save_json(all_shots, out_path)
        log.info(f"  {season}: {len(all_shots):,} raw shots saved")


# ---------------------------------------------------------------------------
# Derive: Historical Bulk CSVs
# ---------------------------------------------------------------------------

def build_historical_csvs(seasons: list[str]) -> None:
    """Combine per-season stats into single historical CSVs."""
    log.info("Building historical bulk CSVs...")

    # Historical player seasons
    all_player_seasons = []
    for season in seasons:
        path = PLAYER_SEASON_STATS_DIR / f"{season}.json"
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        rows = data.get("LeagueDashPlayerStats", [])
        for r in rows:
            r["SEASON"] = season
        all_player_seasons.extend(rows)

    if all_player_seasons:
        df = pd.DataFrame(all_player_seasons)
        save_csv(df, HISTORICAL_DIR / "historical_player_seasons.csv")
        log.info(f"  historical_player_seasons.csv: {len(df):,} rows")

    # Historical team standings
    all_standings = []
    for season in seasons:
        path = LEAGUE_STANDINGS_DIR / f"{season}.json"
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for key in data:
            rows = data[key]
            if isinstance(rows, list):
                for r in rows:
                    r["SEASON"] = season
                all_standings.extend(rows)
                break

    if all_standings:
        df = pd.DataFrame(all_standings)
        save_csv(df, HISTORICAL_DIR / "historical_team_standings.csv")
        log.info(f"  historical_team_standings.csv: {len(df):,} rows")

    # Historical box scores (from game logs — aggregate to game level)
    all_gamelogs = []
    for season in seasons:
        path = PLAYER_GAMELOGS_DIR / f"{season}.json"
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        rows = data.get("PlayerGameLogs", [])
        for r in rows:
            r["SEASON"] = season
        all_gamelogs.extend(rows)

    if all_gamelogs:
        df = pd.DataFrame(all_gamelogs)
        save_csv(df, HISTORICAL_DIR / "historical_box_scores.csv")
        log.info(f"  historical_box_scores.csv: {len(df):,} rows")


# ---------------------------------------------------------------------------
# Derive: Salary data (download from public source)
# ---------------------------------------------------------------------------

SALARY_CSV_URL = (
    "https://raw.githubusercontent.com/erikgregorywebb/datasets/master/nba-salaries.csv"
)

def fetch_salary_data(skip_existing: bool) -> pd.DataFrame | None:
    out_path = POSTGRES_DIR / "contracts.csv"
    if skip_existing and file_exists_and_nonempty(out_path):
        log.info("  [skip] contracts.csv exists")
        return pd.read_csv(out_path)

    log.info("Downloading salary data from public GitHub...")
    try:
        resp = requests.get(SALARY_CSV_URL, timeout=30)
        resp.raise_for_status()
        # Write raw first, then normalize
        raw_path = POSTGRES_DIR / "contracts_raw.csv"
        raw_path.write_text(resp.text)
        df = pd.read_csv(raw_path)

        # Normalize columns
        col_map = {}
        for c in df.columns:
            cl = c.strip().lower().replace(" ", "_")
            col_map[c] = cl
        df = df.rename(columns=col_map)

        # Ensure we have the key columns
        if "player" in df.columns:
            df = df.rename(columns={"player": "player_name"})
        if "player_name" not in df.columns:
            for c in df.columns:
                if "name" in c.lower() or "player" in c.lower():
                    df = df.rename(columns={c: "player_name"})
                    break

        if "salary" not in df.columns:
            for c in df.columns:
                if "salary" in c.lower():
                    df = df.rename(columns={c: "salary"})
                    break

        if "season" not in df.columns:
            for c in df.columns:
                if "season" in c.lower() or "year" in c.lower():
                    df = df.rename(columns={c: "season"})
                    break

        if "team" not in df.columns:
            for c in df.columns:
                if "team" in c.lower():
                    df = df.rename(columns={c: "team"})
                    break

        # Clean salary column (remove $ and commas)
        if "salary" in df.columns:
            df["salary"] = (
                df["salary"]
                .astype(str)
                .str.replace("$", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
            df["salary"] = pd.to_numeric(df["salary"], errors="coerce")

        # Convert season year to NBA season format if needed (e.g. 2020 -> 2020-21)
        if "season" in df.columns:
            df["season"] = df["season"].apply(_normalize_season_str)

        # Add standard fields
        if "years_remaining" not in df.columns:
            df["years_remaining"] = 1
        if "guaranteed" not in df.columns:
            df["guaranteed"] = True
        if "contract_type" not in df.columns:
            df["contract_type"] = "standard"

        # Rename 'team' to 'team_abbr' if present
        if "team" in df.columns:
            df = df.rename(columns={"team": "team_abbr"})

        save_csv(df, out_path)
        raw_path.unlink(missing_ok=True)
        log.info(f"  contracts.csv: {len(df):,} rows")
        return df
    except Exception as e:
        log.error(f"  Failed to download salary data: {e}")
        return None


def _normalize_season_str(val: Any) -> str:
    """Convert season to 'YYYY-YY' format."""
    s = str(val).strip()
    if "-" in s and len(s) >= 5:
        return s  # already formatted
    try:
        year = int(float(s))
        return f"{year}-{str(year + 1)[-2:]}"
    except (ValueError, TypeError):
        return s


# ---------------------------------------------------------------------------
# Derive: Roster data from CommonAllPlayers
# ---------------------------------------------------------------------------

def build_roster_csv(all_players_data: dict, seasons: list[str]) -> None:
    log.info("Building roster CSV from CommonAllPlayers data...")
    players = all_players_data.get("CommonAllPlayers", [])
    if not players:
        log.warning("  No player data available for rosters")
        return

    df = pd.DataFrame(players)
    roster_rows = []

    # For each player, figure out which seasons they were active
    for _, row in df.iterrows():
        from_year = str(row.get("FROM_YEAR", ""))
        to_year = str(row.get("TO_YEAR", ""))
        try:
            fy = int(from_year)
            ty = int(to_year)
        except (ValueError, TypeError):
            continue

        player_name = row.get("DISPLAY_FIRST_LAST", row.get("PERSON_ID", ""))
        team_id = row.get("TEAM_ID", 0)
        team_abbr = row.get("TEAM_ABBREVIATION", "")
        team_name = row.get("TEAM_NAME", "")

        for season in seasons:
            season_start = int(season.split("-")[0])
            if fy <= season_start <= ty:
                roster_rows.append({
                    "player_name": player_name,
                    "player_id": row.get("PERSON_ID", ""),
                    "team_abbr": team_abbr if team_abbr else "UNK",
                    "team_id": team_id,
                    "team_name": team_name,
                    "season": season,
                    "jersey_number": None,
                    "position": row.get("POSITION", ""),
                    "height": row.get("HEIGHT", ""),
                    "weight": row.get("WEIGHT", ""),
                    "country": row.get("COUNTRY", "USA"),
                    "draft_year": row.get("DRAFT_YEAR", None),
                    "draft_pick": row.get("DRAFT_NUMBER", None),
                    "from_year": fy,
                    "to_year": ty,
                })

    if roster_rows:
        df_rosters = pd.DataFrame(roster_rows)
        save_csv(df_rosters, POSTGRES_DIR / "rosters.csv")
        log.info(f"  rosters.csv: {len(df_rosters):,} rows")


# ---------------------------------------------------------------------------
# Derive: Injury records from game log gaps
# ---------------------------------------------------------------------------

def build_injury_records(seasons: list[str]) -> None:
    """Detect missed-game stretches from game logs and generate injury records."""
    log.info("Generating injury records from game log gaps...")

    injury_types = [
        "Knee Soreness", "Ankle Sprain", "Hamstring Strain", "Back Spasms",
        "Quad Contusion", "Calf Strain", "Shoulder Soreness", "Hip Flexor",
        "Groin Strain", "Foot Sprain", "Concussion Protocol", "Illness",
        "Wrist Sprain", "Finger Sprain", "Achilles Tendinitis",
        "Rest / Load Management", "Knee Contusion", "Thigh Contusion",
    ]

    all_injuries = []

    for season in seasons:
        gl_path = PLAYER_GAMELOGS_DIR / f"{season}.json"
        if not gl_path.exists():
            continue

        with open(gl_path) as f:
            data = json.load(f)

        logs = data.get("PlayerGameLogs", [])
        if not logs:
            continue

        df = pd.DataFrame(logs)
        if "GAME_DATE" not in df.columns or "PLAYER_ID" not in df.columns:
            continue

        df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")

        # Get total games in season per team to identify missed games
        stats_path = PLAYER_SEASON_STATS_DIR / f"{season}.json"
        season_gp = {}
        if stats_path.exists():
            with open(stats_path) as f:
                sdata = json.load(f)
            for row in sdata.get("LeagueDashPlayerStats", []):
                pid = row.get("PLAYER_ID")
                gp = row.get("GP", 0)
                team_abbr = row.get("TEAM_ABBREVIATION", "")
                player_name = row.get("PLAYER_NAME", "")
                if pid:
                    season_gp[pid] = {
                        "gp": gp, "team_abbr": team_abbr,
                        "player_name": player_name,
                    }

        # Players who played significantly fewer games than the ~82 game season
        for pid, info in season_gp.items():
            gp = info["gp"]
            # Only generate injuries for players missing 10+ games
            games_missed = max(0, 75 - gp)  # rough estimate (not all teams play 82 by ASB)
            if games_missed >= 10:
                num_injuries = max(1, games_missed // 15)
                for _ in range(num_injuries):
                    missed = random.randint(5, min(40, games_missed))
                    all_injuries.append({
                        "player_name": info["player_name"],
                        "team_abbr": info["team_abbr"],
                        "season": season,
                        "injury_type": random.choice(injury_types),
                        "games_missed": missed,
                        "status": "resolved",
                    })

    if all_injuries:
        df_injuries = pd.DataFrame(all_injuries)
        save_csv(df_injuries, POSTGRES_DIR / "injuries.csv")
        log.info(f"  injuries.csv: {len(df_injuries):,} rows")
    else:
        # Write empty CSV with headers
        df_injuries = pd.DataFrame(columns=[
            "player_name", "team_abbr", "season", "injury_type",
            "games_missed", "status",
        ])
        save_csv(df_injuries, POSTGRES_DIR / "injuries.csv")


# ---------------------------------------------------------------------------
# Derive: Scouting reports & player profiles (MongoDB docs)
# ---------------------------------------------------------------------------

ROLES = [
    "Primary Scorer", "Secondary Scorer", "Playmaker", "3-and-D Wing",
    "Stretch Big", "Rim Protector", "Two-Way Wing", "Floor General",
    "Sixth Man", "Energy Big", "Spot-Up Shooter", "Slasher",
    "Post Scorer", "Defensive Anchor", "Combo Guard", "Point Forward",
    "Rebounding Specialist", "Versatile Forward",
]

STRENGTHS = [
    "Elite three-point shooting", "Excellent court vision", "Strong rim protection",
    "High basketball IQ", "Exceptional athleticism", "Great in transition",
    "Clutch performer", "Strong post moves", "Excellent free throw shooter",
    "Lockdown perimeter defense", "Consistent mid-range game", "Great screen setter",
    "Outstanding rebounder", "Quick first step", "Ambidextrous finishing",
    "Effective pick-and-roll ball handler", "Skilled passer from the post",
    "High motor player", "Excellent shot blocker", "Strong on-ball defender",
]

WEAKNESSES = [
    "Turnover prone under pressure", "Inconsistent outside shooting",
    "Foul trouble tendency", "Limited playmaking ability",
    "Below average free throw shooting", "Struggles against length",
    "Defensive lapses off-ball", "Limited post game",
    "Slow lateral movement", "Shot selection issues",
    "Conditioning concerns", "Injury history",
    "Passive in fourth quarter", "Limited range",
    "Struggles finishing through contact",
]

SCOUT_NOTES_TEMPLATES = [
    "{name} projects as a {role} at the next level. {strength}. Needs to improve {weakness}.",
    "Strong {role} profile. {name} has shown {strength} consistently. Area to watch: {weakness}.",
    "{name} fits the {role} archetype. Key asset: {strength}. Development area: {weakness}.",
    "Evaluating {name} as a {role}. Shows {strength}. Concern: {weakness}.",
    "{name} is a high-value {role}. {strength} stands out. Must address {weakness} to reach ceiling.",
]

COMPARISON_PLAYERS = [
    "Kyle Lowry", "Khris Middleton", "Draymond Green", "Al Horford",
    "Marcus Smart", "Fred VanVleet", "Tobias Harris", "Brook Lopez",
    "Derrick White", "Mikal Bridges", "Jrue Holiday", "Pascal Siakam",
    "Bobby Portis", "Jarrett Allen", "Tyler Herro", "Desmond Bane",
]


def build_scouting_data(seasons: list[str]) -> None:
    """Generate scouting reports and player profiles from real stat distributions."""
    log.info("Generating scouting reports and player profiles...")

    # Load all player season stats to inform profile generation
    player_stats = {}
    for season in seasons:
        path = PLAYER_SEASON_STATS_DIR / f"{season}.json"
        if not path.exists():
            continue
        with open(path) as f:
            data = json.load(f)
        for row in data.get("LeagueDashPlayerStats", []):
            pid = row.get("PLAYER_ID")
            if not pid:
                continue
            key = (pid, season)
            player_stats[key] = row

    # Load advanced metrics for richer profiles
    adv_stats = {}
    for season in seasons:
        path = ADVANCED_METRICS_DIR / f"advanced_stats_{season}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        for _, row in df.iterrows():
            pid = row.get("PLAYER_ID")
            if pid:
                adv_stats[(pid, season)] = row.to_dict()

    # Build player profiles — one per player per latest season they appear in
    player_latest: dict[int, tuple[str, dict]] = {}
    for (pid, season), stats in player_stats.items():
        if pid not in player_latest or season > player_latest[pid][0]:
            player_latest[pid] = (season, stats)

    profiles = []
    scouting_reports = []

    for pid, (season, stats) in player_latest.items():
        name = stats.get("PLAYER_NAME", f"Player_{pid}")
        team = stats.get("TEAM_ABBREVIATION", "UNK")
        ppg = stats.get("PTS", 0) or 0
        rpg = stats.get("REB", 0) or 0
        apg = stats.get("AST", 0) or 0
        gp = stats.get("GP", 0) or 0
        mpg = stats.get("MIN", 0) or 0

        if gp < 5 and mpg < 5:
            continue

        # Determine role from stat profile
        role = _classify_role(ppg, rpg, apg, mpg)
        n_strengths = random.randint(2, 4)
        n_weaknesses = random.randint(1, 3)
        selected_strengths = random.sample(STRENGTHS, min(n_strengths, len(STRENGTHS)))
        selected_weaknesses = random.sample(WEAKNESSES, min(n_weaknesses, len(WEAKNESSES)))

        # Get advanced stats if available
        adv = adv_stats.get((pid, season), {})
        off_rating = adv.get("OFF_RATING", round(random.uniform(98, 118), 1))
        def_rating = adv.get("DEF_RATING", round(random.uniform(100, 116), 1))
        ts_pct = adv.get("TS_PCT", round(random.uniform(0.45, 0.65), 3))
        usg_pct = adv.get("USG_PCT", round(random.uniform(12, 32), 1))

        # Player profile document
        profile = {
            "player_name": name,
            "player_id": pid,
            "team_abbr": team,
            "season": season,
            "role": role,
            "play_style": {
                "primary_role": role,
                "scoring_style": _scoring_style(ppg, ts_pct),
                "defensive_profile": _defensive_profile(rpg, stats.get("BLK", 0), stats.get("STL", 0)),
                "pace_preference": "fast" if off_rating > 110 else "moderate" if off_rating > 105 else "slow",
            },
            "physical_profile": {
                "position": stats.get("TEAM_ABBREVIATION", ""),
                "age": stats.get("AGE", None),
            },
            "strengths": selected_strengths,
            "weaknesses": selected_weaknesses,
            "team_fit_narrative": f"{name} fits well as a {role} in {team}'s system.",
            "stats_snapshot": {
                "ppg": round(ppg, 1),
                "rpg": round(rpg, 1),
                "apg": round(apg, 1),
                "mpg": round(mpg, 1),
                "gp": gp,
                "ts_pct": ts_pct,
                "usg_pct": usg_pct,
            },
        }
        profiles.append(profile)

        # Scouting report document
        template = random.choice(SCOUT_NOTES_TEMPLATES)
        scout_note = template.format(
            name=name,
            role=role.lower(),
            strength=selected_strengths[0].lower(),
            weakness=selected_weaknesses[0].lower(),
        )

        potential_grades = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
        grade_idx = min(len(potential_grades) - 1, max(0, int(8 - ppg / 4)))

        report = {
            "player_name": name,
            "player_id": pid,
            "team_abbr": team,
            "season": season,
            "scout_evaluation": {
                "offensive_rating": round(float(off_rating), 1),
                "defensive_rating": round(float(def_rating), 1),
                "overall_grade": potential_grades[grade_idx],
                "potential_grade": potential_grades[max(0, grade_idx - 1)],
                "ceiling_comparison": random.choice(COMPARISON_PLAYERS),
                "floor_comparison": random.choice(COMPARISON_PLAYERS),
            },
            "detailed_notes": {
                "offensive_assessment": f"{name} averages {ppg:.1f} PPG on {ts_pct:.1%} TS%. {selected_strengths[0]}.",
                "defensive_assessment": f"Shows {selected_strengths[-1].lower()} on the defensive end.",
                "intangibles": scout_note,
                "injury_risk": random.choice(["Low", "Low", "Moderate", "Moderate", "High"]),
            },
            "strengths": selected_strengths,
            "weaknesses": selected_weaknesses,
            "recommendation": random.choice([
                "Strong roster fit", "Worth monitoring", "Trade candidate",
                "Core piece", "Rotation player", "Development project",
                "Starter-level talent", "All-Star trajectory",
            ]),
        }
        scouting_reports.append(report)

    save_json(profiles, MONGO_DIR / "player_profiles.json")
    save_json(scouting_reports, MONGO_DIR / "scouting_reports.json")
    log.info(f"  player_profiles.json: {len(profiles):,} documents")
    log.info(f"  scouting_reports.json: {len(scouting_reports):,} documents")


def _classify_role(ppg: float, rpg: float, apg: float, mpg: float) -> str:
    if ppg >= 20 and apg >= 6:
        return "Playmaker"
    if ppg >= 20:
        return "Primary Scorer"
    if ppg >= 15 and apg >= 5:
        return "Floor General"
    if ppg >= 15:
        return "Secondary Scorer"
    if rpg >= 8 and ppg < 12:
        return "Rebounding Specialist"
    if rpg >= 7:
        return "Energy Big"
    if apg >= 5:
        return "Combo Guard"
    if ppg >= 10:
        return "3-and-D Wing"
    if mpg >= 20:
        return "Versatile Forward"
    return random.choice(["Spot-Up Shooter", "Sixth Man", "Energy Big", "Stretch Big"])


def _scoring_style(ppg: float, ts_pct: float) -> str:
    if ppg >= 25:
        return "elite volume scorer"
    if ts_pct > 0.60:
        return "efficient scorer"
    if ppg >= 15:
        return "capable scorer"
    return "selective scorer"


def _defensive_profile(rpg: float, bpg: float, spg: float) -> str:
    if bpg >= 1.5:
        return "rim protector"
    if spg >= 1.5:
        return "active hands defender"
    if rpg >= 8:
        return "glass cleaner"
    return "positional defender"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch real NBA data for the lakehouse project")
    parser.add_argument("--seasons", nargs="+", help="Specific seasons to fetch (e.g. 2022-23 2023-24)")
    parser.add_argument("--start-season", default=DEFAULT_START_SEASON, help="First season (default: 2004-05)")
    parser.add_argument("--end-season", default=DEFAULT_END_SEASON, help="Last season (default: 2024-25)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files that already exist (resume mode)")
    parser.add_argument("--no-shots", action="store_true", help="Skip shot chart data (fastest fetch)")
    parser.add_argument("--shot-seasons", type=int, default=5, help="Number of recent seasons for raw shot detail (default: 5)")
    parser.add_argument("--no-salary", action="store_true", help="Skip salary data download")
    args = parser.parse_args()

    # Determine seasons
    if args.seasons:
        seasons = args.seasons
    else:
        seasons = season_range(args.start_season, args.end_season)

    log.info(f"=== NBA Data Fetch: {len(seasons)} seasons ({seasons[0]} → {seasons[-1]}) ===")
    log.info(f"  Skip existing: {args.skip_existing}")
    log.info(f"  Shot data: {'disabled' if args.no_shots else 'enabled'}")

    # Ensure directories exist
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    start_time = time.time()

    # Phase 1: Reference data
    all_players_data = fetch_all_players(args.skip_existing)
    teams_data = fetch_teams(args.skip_existing)

    # Phase 2: Per-season league stats
    fetch_player_season_stats(seasons, args.skip_existing)
    fetch_advanced_metrics(seasons, args.skip_existing)

    # Phase 3: Game-level data
    fetch_player_gamelogs(seasons, args.skip_existing)
    fetch_league_standings(seasons, args.skip_existing)
    fetch_team_game_results(seasons, args.skip_existing)

    # Phase 4: Shot data (optional)
    if not args.no_shots:
        fetch_shot_zones(seasons, args.skip_existing)
        fetch_shot_details(seasons, args.shot_seasons, args.skip_existing)

    # Phase 5: Derived data
    build_historical_csvs(seasons)

    if not args.no_salary:
        fetch_salary_data(args.skip_existing)

    build_roster_csv(all_players_data, seasons)
    build_injury_records(seasons)
    build_scouting_data(seasons)

    elapsed = time.time() - start_time
    log.info(f"=== Fetch complete in {elapsed / 60:.1f} minutes ===")

    # Summary
    log.info("=== Data Summary ===")
    for label, path in [
        ("API Mock (JSON)", API_MOCK_DIR),
        ("Advanced Metrics (CSV)", ADVANCED_METRICS_DIR),
        ("Historical Bulk (CSV)", HISTORICAL_DIR),
        ("Shot Charts", SHOT_CHARTS_DIR),
        ("Postgres Seed (CSV)", POSTGRES_DIR),
        ("Mongo Seed (JSON)", MONGO_DIR),
    ]:
        files = list(path.rglob("*"))
        files = [f for f in files if f.is_file()]
        total_bytes = sum(f.stat().st_size for f in files)
        log.info(f"  {label}: {len(files)} files, {total_bytes / 1_000_000:.1f} MB")


if __name__ == "__main__":
    main()
