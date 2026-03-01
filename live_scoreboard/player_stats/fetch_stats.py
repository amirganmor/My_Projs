"""
Batch fetcher for player season statistics.

Fetches from nba_api and ESPN, writes/upserts into player_season_stats table.
Runs in a loop with a configurable sleep interval (default 6 hours).
"""

import os
import time
import json
import logging
import requests
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB", "scoreboard")
PG_USER = os.getenv("POSTGRES_USER", "scoreboard")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "scoreboard")
FETCH_INTERVAL = int(os.getenv("FETCH_INTERVAL_HOURS", "6")) * 3600

CURRENT_NBA_SEASON = "2025-26"
CURRENT_NFL_SEASON = "2025"
CURRENT_SOCCER_SEASON = "2025"


def get_conn():
    """Create and return a new PostgreSQL connection."""
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT, dbname=PG_DB,
        user=PG_USER, password=PG_PASS,
    )


def upsert_stats(conn, rows):
    """Upsert player stat rows into player_season_stats.

    rows: list of (league, season, player_name, team, games_played, stats_dict)
    """
    if not rows:
        return
    sql = """
        INSERT INTO player_season_stats (league, season, player_name, team, games_played, stats, updated_at)
        VALUES %s
        ON CONFLICT (league, season, player_name, team)
        DO UPDATE SET games_played = EXCLUDED.games_played,
                      stats = EXCLUDED.stats,
                      updated_at = EXCLUDED.updated_at
    """
    now = datetime.utcnow()
    values = [(r[0], r[1], r[2], r[3], r[4], json.dumps(r[5]), now) for r in rows]
    with conn.cursor() as cur:
        execute_values(cur, sql, values)
    conn.commit()


def fetch_nba_stats():
    """Fetch NBA season player stats via nba_api."""
    logger.info("Fetching NBA player stats...")
    rows = []
    try:
        from nba_api.stats.endpoints import leaguedashplayerstats
        data = leaguedashplayerstats.LeagueDashPlayerStats(
            season=CURRENT_NBA_SEASON,
            per_mode_detailed="PerGame",
        )
        players = data.get_normalized_dict()["LeagueDashPlayerStats"]
        for p in players:
            stats = {
                "points": p.get("PTS", 0),
                "rebounds": p.get("REB", 0),
                "assists": p.get("AST", 0),
                "steals": p.get("STL", 0),
                "blocks": p.get("BLK", 0),
                "turnovers": p.get("TOV", 0),
                "fg_pct": p.get("FG_PCT", 0),
                "fg3_pct": p.get("FG3_PCT", 0),
                "ft_pct": p.get("FT_PCT", 0),
                "minutes": p.get("MIN", 0),
            }
            rows.append((
                "nba", CURRENT_NBA_SEASON,
                p.get("PLAYER_NAME", "Unknown"),
                p.get("TEAM_ABBREVIATION", ""),
                p.get("GP", 0),
                stats,
            ))
        logger.info("  NBA: %d players fetched", len(rows))
    except Exception as e:
        logger.error("  NBA fetch error: %s", e)
    return rows


def fetch_espn_football_stats(league, league_slug, season):
    """Fetch NFL player stats from ESPN by category (passing, rushing, receiving)."""
    logger.info("Fetching %s player stats...", league.upper())
    rows = []
    categories = ["passing", "rushing", "receiving"]
    for cat in categories:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/football/{league_slug}/statistics?season={season}&category={cat}"
            resp = requests.get(url, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for leader in data.get("leaders", []):
                for entry in leader.get("leaders", []):
                    athlete = entry.get("athlete", {})
                    team = athlete.get("team", {}).get("abbreviation", "")
                    name = athlete.get("displayName", "Unknown")
                    stat_val = entry.get("value", 0)
                    stat_name = leader.get("name", cat)
                    rows.append((
                        league, season, name, team, 0,
                        {stat_name: stat_val, "category": cat},
                    ))
            time.sleep(0.5)
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            logger.error("  %s %s fetch error: %s", league.upper(), cat, e)
    logger.info("  %s: %d stat entries fetched", league.upper(), len(rows))
    return rows


def fetch_espn_soccer_stats(league, league_slug, season):
    """Fetch soccer player stats from ESPN leaders endpoint."""
    logger.info("Fetching %s player stats...", league.upper())
    rows = []
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/statistics?season={season}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/leaders?season={season}"
            resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            logger.warning("  %s: API returned %d", league.upper(), resp.status_code)
            return rows

        data = resp.json()
        for leader_cat in data.get("leaders", []):
            cat_name = leader_cat.get("name", "")
            for entry in leader_cat.get("leaders", []):
                athlete = entry.get("athlete", {})
                team = athlete.get("team", {}).get("displayName", "")
                name = athlete.get("displayName", "Unknown")
                stat_val = entry.get("value", 0)
                rows.append((
                    league, season, name, team, 0,
                    {cat_name: stat_val},
                ))
        time.sleep(0.5)
    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        logger.error("  %s fetch error: %s", league.upper(), e)
    logger.info("  %s: %d stat entries fetched", league.upper(), len(rows))
    return rows


def run_fetch_cycle():
    """Run one full fetch cycle for all leagues, upserting results to Postgres."""
    logger.info("=== Player Stats Fetch Cycle: %s ===", datetime.utcnow().isoformat())
    conn = get_conn()
    try:
        nba = fetch_nba_stats()
        upsert_stats(conn, nba)

        nfl = fetch_espn_football_stats("nfl", "nfl", CURRENT_NFL_SEASON)
        upsert_stats(conn, nfl)

        pl = fetch_espn_soccer_stats("premier_league", "eng.1", CURRENT_SOCCER_SEASON)
        upsert_stats(conn, pl)

        ll = fetch_espn_soccer_stats("la_liga", "esp.1", CURRENT_SOCCER_SEASON)
        upsert_stats(conn, ll)

        cl = fetch_espn_soccer_stats("champions_league", "uefa.champions", CURRENT_SOCCER_SEASON)
        upsert_stats(conn, cl)

        logger.info("=== Fetch cycle complete ===")
    except Exception as e:
        logger.error("Fetch cycle error: %s", e)
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("Player stats fetcher starting. Interval: %ds", FETCH_INTERVAL)
    while True:
        try:
            run_fetch_cycle()
        except Exception as e:
            logger.error("Top-level error: %s", e)
        logger.info("Sleeping %ds until next fetch...", FETCH_INTERVAL)
        time.sleep(FETCH_INTERVAL)
