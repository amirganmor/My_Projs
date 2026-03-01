"""
NBA live scoreboard producer.

Fetches live game data from nba_api and ESPN, enriches with play-by-play
coordinates and box score stats, then publishes to Kafka.
"""

import re
import time
import json
import os
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from kafka import KafkaProducer
from nba_api.live.nba.endpoints import scoreboard, playbyplay, boxscore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = "nba_scores"

ESPN_NBA_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_NBA_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event={event_id}"

RECENT_PLAYS_LIMIT = 30
MAX_CLOCK_DISTANCE = 999
CLOCK_MATCH_TOLERANCE = 3
ESPN_COORD_ABS_LIMIT = 1000

producer = KafkaProducer(
    bootstrap_servers=[KAFKA_BOOTSTRAP],
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

pbp_cache = {}
pbp_ts = {}
PBP_TTL = 5

bs_cache = {}
bs_ts = {}
BS_TTL = 10

espn_map_cache = {}
espn_map_ts = 0
ESPN_MAP_TTL = 60

espn_plays_cache = {}
espn_plays_ts = {}
ESPN_PLAYS_TTL = 5

NOT_STARTED_RE = re.compile(r"\d{1,2}:\d{2}\s*(pm|am)", re.IGNORECASE)


def _parse_clock_seconds(display_val):
    """Parse a clock display value like '5:30' or '17.4' to total seconds."""
    try:
        s = str(display_val).strip()
        if ":" in s:
            parts = s.split(":")
            return int(parts[0]) * 60 + float(parts[1])
        return float(s)
    except (ValueError, IndexError):
        return -1


def _parse_iso_seconds(iso):
    """Parse ISO duration 'PT05M30.00S' to total seconds."""
    try:
        s = iso.replace("PT", "").replace("S", "")
        parts = s.split("M")
        m = int(parts[0])
        sec = float(parts[1]) if len(parts) > 1 else 0
        return m * 60 + sec
    except (ValueError, IndexError):
        return -1


def fetch_espn_game_map():
    """Return mapping: frozenset({home_abbrev, away_abbrev}) -> espn_event_id."""
    global espn_map_cache, espn_map_ts
    now = time.time()
    if espn_map_cache and (now - espn_map_ts) < ESPN_MAP_TTL:
        return espn_map_cache

    try:
        resp = requests.get(ESPN_NBA_SCOREBOARD, timeout=10)
        resp.raise_for_status()
        events = resp.json().get("events", [])
        mapping = {}
        for ev in events:
            eid = ev["id"]
            competitions = ev.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            abbrevs = set()
            for c in comp.get("competitors", []):
                abbrevs.add(c["team"]["abbreviation"])
            if len(abbrevs) == 2:
                mapping[frozenset(abbrevs)] = eid
        espn_map_cache = mapping
        espn_map_ts = now
        return mapping
    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        logger.warning("ESPN NBA scoreboard fetch error: %s", e)
        return espn_map_cache


def fetch_espn_plays(espn_event_id):
    """Fetch ESPN NBA summary plays with coordinates.

    Returns list of (period, clock_seconds, x, y) tuples for plays with real coords.
    """
    now = time.time()
    if espn_event_id in espn_plays_cache and (now - espn_plays_ts.get(espn_event_id, 0)) < ESPN_PLAYS_TTL:
        return espn_plays_cache[espn_event_id]

    try:
        time.sleep(0.15)
        resp = requests.get(ESPN_NBA_SUMMARY.format(event_id=espn_event_id), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError):
        return espn_plays_cache.get(espn_event_id, [])

    coord_list = []
    for p in data.get("plays", []):
        coord = p.get("coordinate", {})
        x, y = coord.get("x"), coord.get("y")
        if x is None or y is None or abs(x) > ESPN_COORD_ABS_LIMIT:
            continue
        period = p.get("period", {}).get("number", 0)
        clock_str = p.get("clock", {}).get("displayValue", "0")
        secs = _parse_clock_seconds(clock_str)
        coord_list.append((period, secs, x, y))

    espn_plays_cache[espn_event_id] = coord_list
    espn_plays_ts[espn_event_id] = now
    return coord_list


def _find_espn_coord(espn_coords, period, clock_secs):
    """Find the closest ESPN coordinate for a given period and clock."""
    best = None
    best_dist = MAX_CLOCK_DISTANCE
    for ep, es, ex, ey in espn_coords:
        if ep != period:
            continue
        dist = abs(es - clock_secs)
        if dist < best_dist:
            best_dist = dist
            best = (ex, ey)
    if best_dist <= CLOCK_MATCH_TOLERANCE:
        return best
    return None


def extract_periods(raw_game):
    """Extract per-period scores from a raw NBA API game object."""
    periods = []
    home_periods = raw_game.get("homeTeam", {}).get("periods", [])
    away_periods = raw_game.get("awayTeam", {}).get("periods", [])
    for i, (hp, ap) in enumerate(zip(home_periods, away_periods)):
        periods.append({
            "period": i + 1,
            "homeScore": hp.get("score", 0),
            "awayScore": ap.get("score", 0),
        })
    return periods


def format_clock(iso_clock):
    """Convert ISO clock 'PT05M30.00S' to display format '5:30'."""
    try:
        s = iso_clock.replace("PT", "").replace("S", "")
        parts = s.split("M")
        mins = int(parts[0])
        secs = int(float(parts[1])) if len(parts) > 1 else 0
        return f"{mins}:{secs:02d}"
    except (ValueError, IndexError):
        return iso_clock


def fetch_plays(game_id, status_text, espn_coords):
    """Fetch recent play-by-play, merging ESPN coordinates for plays missing them."""
    if "Final" in status_text:
        return pbp_cache.get(game_id, [])

    now = time.time()
    if game_id in pbp_cache and (now - pbp_ts.get(game_id, 0)) < PBP_TTL:
        return pbp_cache[game_id]

    try:
        pbp = playbyplay.PlayByPlay(game_id)
        actions = pbp.get_dict().get("game", {}).get("actions", [])
        plays = []
        for a in actions[-RECENT_PLAYS_LIMIT:]:
            play = {
                "clock": format_clock(a.get("clock", "")),
                "period": a.get("period", 0),
                "description": a.get("description", ""),
                "team": a.get("teamTricode", ""),
                "scoreHome": str(a.get("scoreHome", "")),
                "scoreAway": str(a.get("scoreAway", "")),
                "actionType": a.get("actionType", ""),
                "subType": a.get("subType", ""),
                "shotResult": a.get("shotResult", ""),
                "playerName": a.get("playerNameI", ""),
                "area": a.get("area", ""),
                "areaDetail": a.get("areaDetail", ""),
                "shotDistance": a.get("shotDistance"),
            }
            x, y = a.get("x"), a.get("y")
            if x is not None and y is not None:
                play["x"] = round(x, 2)
                play["y"] = round(y, 2)
            elif espn_coords:
                clock_secs = _parse_iso_seconds(a.get("clock", ""))
                match = _find_espn_coord(espn_coords, play["period"], clock_secs)
                if match:
                    play["espnX"] = match[0]
                    play["espnY"] = match[1]
            plays.append(play)
        pbp_cache[game_id] = plays
        pbp_ts[game_id] = now
        return plays
    except Exception as e:
        logger.warning("PBP fetch error for %s: %s", game_id, e)
        return pbp_cache.get(game_id, [])


def _fmt_min(iso):
    """Format ISO duration to 'M:SS' for display."""
    try:
        s = iso.replace("PT", "").replace("S", "")
        parts = s.split("M")
        m = int(parts[0])
        sec = int(float(parts[1])) if len(parts) > 1 else 0
        return f"{m}:{sec:02d}"
    except (ValueError, IndexError):
        return iso or "0:00"


def _fmt_shooting(made, att, pct):
    """Format shooting stats as 'made/att (pct%)'."""
    return f"{made}/{att} ({pct:.1f}%)" if att else f"{made}/{att}"


def _extract_player(p):
    """Extract normalized player stats from a box score player entry."""
    st = p.get("statistics", {})
    return {
        "name": p.get("name", ""),
        "starter": p.get("starter", "0") == "1",
        "position": p.get("position", ""),
        "minutes": _fmt_min(st.get("minutes", "PT0M0.00S")),
        "points": st.get("points", 0),
        "rebounds": st.get("reboundsTotal", 0),
        "assists": st.get("assists", 0),
        "steals": st.get("steals", 0),
        "blocks": st.get("blocks", 0),
        "fg": f"{st.get('fieldGoalsMade', 0)}/{st.get('fieldGoalsAttempted', 0)}",
        "threePt": f"{st.get('threePointersMade', 0)}/{st.get('threePointersAttempted', 0)}",
        "ft": f"{st.get('freeThrowsMade', 0)}/{st.get('freeThrowsAttempted', 0)}",
        "offReb": st.get("reboundsOffensive", 0),
        "defReb": st.get("reboundsDefensive", 0),
        "turnovers": st.get("turnovers", 0),
        "fouls": st.get("foulsPersonal", 0),
        "plusMinus": st.get("plusMinusPoints", 0),
    }


def _extract_team_stats(ts):
    """Extract aggregated team shooting and stat totals."""
    fgm = ts.get("fieldGoalsMade", 0)
    fga = ts.get("fieldGoalsAttempted", 0)
    fgp = ts.get("fieldGoalsPercentage", 0.0)
    tpm = ts.get("threePointersMade", 0)
    tpa = ts.get("threePointersAttempted", 0)
    tpp = ts.get("threePointersPercentage", 0.0)
    ftm = ts.get("freeThrowsMade", 0)
    fta = ts.get("freeThrowsAttempted", 0)
    ftp = ts.get("freeThrowsPercentage", 0.0)
    return {
        "fieldGoals": _fmt_shooting(fgm, fga, fgp),
        "threePointers": _fmt_shooting(tpm, tpa, tpp),
        "freeThrows": _fmt_shooting(ftm, fta, ftp),
        "assists": str(ts.get("assists", 0)),
        "rebounds": str(ts.get("reboundsTotal", 0)),
        "offRebounds": str(ts.get("reboundsOffensive", 0)),
        "defRebounds": str(ts.get("reboundsDefensive", 0)),
        "steals": str(ts.get("steals", 0)),
        "blocks": str(ts.get("blocks", 0)),
        "turnovers": str(ts.get("turnovers", 0)),
        "fastBreakPts": str(ts.get("pointsFastBreak", 0)),
        "pointsOffTurnovers": str(ts.get("pointsFromTurnovers", 0)),
        "pointsInPaint": str(ts.get("pointsInThePaint", 0)),
        "personalFouls": str(ts.get("foulsPersonal", 0)),
        "secondChancePts": str(ts.get("pointsSecondChance", 0)),
        "biggestLead": str(ts.get("biggestLead", 0)),
    }


def fetch_boxscore(game_id, status_text):
    """Fetch player box score and team totals for a game."""
    if NOT_STARTED_RE.search(status_text):
        return None

    now = time.time()
    if game_id in bs_cache and (now - bs_ts.get(game_id, 0)) < BS_TTL:
        return bs_cache[game_id]

    try:
        bs = boxscore.BoxScore(game_id=game_id).get_dict()
        game = bs.get("game", {})
        home = game.get("homeTeam", {})
        away = game.get("awayTeam", {})

        home_players = [_extract_player(p) for p in home.get("players", []) if p.get("played", "0") == "1" or p.get("starter", "0") == "1"]
        away_players = [_extract_player(p) for p in away.get("players", []) if p.get("played", "0") == "1" or p.get("starter", "0") == "1"]

        home_stats = _extract_team_stats(home.get("statistics", {}))
        away_stats = _extract_team_stats(away.get("statistics", {}))

        stats = {}
        for key in home_stats:
            stats[key] = [home_stats[key], away_stats.get(key, "0")]

        result = {
            "boxscore": {
                "home": {"players": home_players},
                "away": {"players": away_players},
            },
            "stats": stats,
        }
        bs_cache[game_id] = result
        bs_ts[game_id] = now
        return result
    except Exception as e:
        logger.warning("Boxscore fetch error for %s: %s", game_id, e)
        return bs_cache.get(game_id, None)


def _resolve_espn_coords(tricode_home, tricode_away, status_text):
    """Resolve ESPN event and fetch coordinate data for a game."""
    if NOT_STARTED_RE.search(status_text):
        return []
    espn_map = fetch_espn_game_map()
    key = frozenset({tricode_home, tricode_away})
    espn_eid = espn_map.get(key)
    if not espn_eid:
        return []
    return fetch_espn_plays(espn_eid)


def normalize_games(raw_games):
    """Normalize raw NBA API games into the unified Kafka message format."""
    results = []
    for g in raw_games:
        gid = g["gameId"]
        status = g["gameStatusText"]
        home_tri = g["homeTeam"].get("teamTricode", "")
        away_tri = g["awayTeam"].get("teamTricode", "")

        espn_coords = _resolve_espn_coords(home_tri, away_tri, status)

        bs_data = fetch_boxscore(gid, status)
        game = {
            "gameId": gid,
            "statusText": status,
            "homeTeam": {"teamName": g["homeTeam"]["teamName"], "score": g["homeTeam"]["score"], "tricode": home_tri},
            "awayTeam": {"teamName": g["awayTeam"]["teamName"], "score": g["awayTeam"]["score"], "tricode": away_tri},
            "periods": extract_periods(g),
            "events": [],
            "plays": fetch_plays(gid, status, espn_coords),
        }
        if bs_data:
            game["boxscore"] = bs_data["boxscore"]
            game["stats"] = bs_data["stats"]
        results.append(game)
    return results


def fingerprint(games):
    """Create a change-detection fingerprint from current game states."""
    parts = [
        f"{g['gameId']}_{g['homeTeam']['score']}_{g['awayTeam']['score']}_{g['statusText']}_{len(g.get('plays', []))}"
        for g in games
    ]
    return "|".join(parts)


def display(games):
    """Print a formatted NBA scoreboard summary to the terminal."""
    print("\033c", end="")
    print("=" * 60)
    print(f"{'NBA LIVE SCOREBOARD':^60}")
    print("=" * 60)
    for g in games:
        home = f"{g['homeTeam']['teamName']} ({g['homeTeam']['score']})"
        away = f"{g['awayTeam']['teamName']} ({g['awayTeam']['score']})"
        plays = g.get("plays", [])
        with_coord = sum(1 for p in plays if p.get("x") is not None or p.get("espnX") is not None)
        print(f"  {away:25} @ {home:25} | {g['statusText']}  coords={with_coord}/{len(plays)}")
    print("=" * 60)


def start_engine():
    """Main loop: fetch NBA data, fingerprint, publish to Kafka."""
    last_fp = None
    logger.info("Starting NBA producer -> %s via %s", KAFKA_TOPIC, KAFKA_BOOTSTRAP)

    while True:
        try:
            raw = scoreboard.ScoreBoard().games.get_dict()
            if raw:
                games = normalize_games(raw)
                display(games)

                fp = fingerprint(games)
                if fp != last_fp:
                    producer.send(KAFKA_TOPIC, value={"league": "nba", "games": games})
                    producer.flush()
                    last_fp = fp

            time.sleep(5)
        except Exception as e:
            logger.error("NBA Engine Error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    start_engine()
