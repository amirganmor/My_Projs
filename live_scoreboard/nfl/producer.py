"""
NFL live scoreboard producer.

Fetches live game data from ESPN, extracts drives, plays, scoring plays,
and team stats, then publishes to Kafka.
"""

import time
import json
import os
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from kafka import KafkaProducer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = "nfl_scores"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={event_id}"

SKIP_STATUSES = {"Scheduled", "Postponed", "Canceled"}
LIVE_STATUSES = {"In Progress", "Halftime", "End of Period", "Overtime"}
SUMMARY_TTL_DEFAULT = 30
SUMMARY_TTL_LIVE = 5
MAX_FETCH_WORKERS = 6
MAX_DRIVES = 10
MAX_PLAYS = 40
EMPTY_DETAILS = {"plays": [], "scoringPlays": [], "drives": [], "stats": {}, "currentDrive": None}

producer = KafkaProducer(
    bootstrap_servers=[KAFKA_BOOTSTRAP],
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

summary_cache = {}
summary_ts = {}


def _summary_ttl(status):
    """Return cache TTL based on game status."""
    return SUMMARY_TTL_LIVE if status in LIVE_STATUSES else SUMMARY_TTL_DEFAULT


def extract_periods(home_comp, away_comp):
    """Extract per-period scores from competitor linescores."""
    periods = []
    home_ls = home_comp.get("linescores", [])
    away_ls = away_comp.get("linescores", [])
    for i, (hl, al) in enumerate(zip(home_ls, away_ls)):
        periods.append({
            "period": i + 1,
            "homeScore": int(hl.get("value", 0)),
            "awayScore": int(al.get("value", 0)),
        })
    return periods


def _extract_play(p):
    """Extract a normalized play dict from an ESPN drive play."""
    ps = p.get("start", {})
    pe = p.get("end", {})
    return {
        "id": p.get("id", ""),
        "text": p.get("text", ""),
        "type": p.get("type", {}).get("text", ""),
        "period": p.get("period", {}).get("number", 0),
        "clock": p.get("clock", {}).get("displayValue", ""),
        "homeScore": p.get("homeScore", 0),
        "awayScore": p.get("awayScore", 0),
        "scoringPlay": p.get("scoringPlay", False),
        "yardsGained": p.get("statYardage", 0),
        "startYardsToEndzone": ps.get("yardsToEndzone"),
        "endYardsToEndzone": pe.get("yardsToEndzone"),
        "down": ps.get("down", 0),
        "distance": ps.get("distance", 0),
        "downDistanceText": pe.get("downDistanceText", ""),
        "possessionText": pe.get("possessionText", ""),
    }


def _extract_drive(dr):
    """Extract a normalized drive summary."""
    team = dr.get("team", {})
    start = dr.get("start", {})
    end = dr.get("end", {})
    return {
        "id": dr.get("id", ""),
        "team": team.get("displayName", ""),
        "teamAbbrev": team.get("abbreviation", ""),
        "result": dr.get("displayResult", ""),
        "yards": dr.get("yards", 0),
        "numPlays": dr.get("offensivePlays", 0),
        "timeElapsed": dr.get("timeElapsed", {}).get("displayValue", ""),
        "isScore": dr.get("isScore", False),
        "startYardLine": start.get("yardLine"),
        "startText": start.get("text", ""),
        "endYardLine": end.get("yardLine"),
        "endText": end.get("text", ""),
    }


def _extract_team_stats(teams):
    """Extract team comparison stats from boxscore."""
    if len(teams) < 2:
        return {}
    stats = {}
    for t in teams:
        ha = "home" if t.get("homeAway") == "home" else "away"
        for s in t.get("statistics", []):
            name = s.get("name", "")
            val = s.get("displayValue", "")
            if name not in stats:
                stats[name] = {}
            stats[name][ha] = val
    result = {}
    for name, vals in stats.items():
        result[name] = [vals.get("home", ""), vals.get("away", "")]
    return result


def fetch_match_details(event_id, status):
    """Fetch full drives, plays, boxscore, and scoring plays from ESPN summary."""
    if status in SKIP_STATUSES:
        return summary_cache.get(event_id, dict(EMPTY_DETAILS))

    now = time.time()
    ttl = _summary_ttl(status)
    if event_id in summary_cache and (now - summary_ts.get(event_id, 0)) < ttl:
        return summary_cache[event_id]

    try:
        time.sleep(0.15)
        resp = requests.get(SUMMARY_URL.format(event_id=event_id), timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        logger.warning("NFL summary fetch failed for %s: %s", event_id, e)
        return summary_cache.get(event_id, dict(EMPTY_DETAILS))

    scoring_plays = []
    for sp in data.get("scoringPlays", []):
        scoring_plays.append({
            "clock": sp.get("clock", {}).get("displayValue", ""),
            "period": sp.get("period", {}).get("number", 0),
            "text": sp.get("text", ""),
            "team": sp.get("team", {}).get("displayName", ""),
            "homeScore": sp.get("homeScore", 0),
            "awayScore": sp.get("awayScore", 0),
            "scoringType": sp.get("type", {}).get("text", ""),
        })

    drives_raw = data.get("drives", {})
    prev_drives = drives_raw.get("previous", [])
    drives = [_extract_drive(dr) for dr in prev_drives]

    all_plays = []
    for dr in prev_drives:
        team_abbrev = dr.get("team", {}).get("abbreviation", "")
        for p in dr.get("plays", []):
            play = _extract_play(p)
            play["driveTeam"] = team_abbrev
            all_plays.append(play)

    current_drive = None
    cur_raw = drives_raw.get("current")
    if cur_raw:
        current_drive = _extract_drive(cur_raw)
        for p in cur_raw.get("plays", []):
            play = _extract_play(p)
            play["driveTeam"] = cur_raw.get("team", {}).get("abbreviation", "")
            all_plays.append(play)

    recent_plays = all_plays[-MAX_PLAYS:]

    bs = data.get("boxscore", {})
    stats = _extract_team_stats(bs.get("teams", []))

    result = {
        "plays": recent_plays,
        "scoringPlays": scoring_plays,
        "drives": drives[-MAX_DRIVES:],
        "stats": stats,
        "currentDrive": current_drive,
    }
    summary_cache[event_id] = result
    summary_ts[event_id] = now
    return result


def fetch_games():
    """Fetch all NFL games from ESPN scoreboard and enrich with match details."""
    resp = requests.get(ESPN_URL, timeout=15)
    resp.raise_for_status()
    events = resp.json().get("events", [])

    details = {}
    with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as pool:
        futures = {}
        for event in events:
            eid = event["id"]
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            status = competitions[0].get("status", {}).get("type", {}).get("description", "")
            futures[pool.submit(fetch_match_details, eid, status)] = eid
        for fut in as_completed(futures):
            eid = futures[fut]
            try:
                details[eid] = fut.result()
            except Exception:
                details[eid] = dict(EMPTY_DETAILS)

    games = []
    for event in events:
        competitions = event.get("competitions", [])
        if not competitions:
            continue
        comp = competitions[0]
        competitors = comp.get("competitors", [])
        home = next((t for t in competitors if t.get("homeAway") == "home"), None)
        away = next((t for t in competitors if t.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        status = comp.get("status", {}).get("type", {}).get("description", "")
        eid = event["id"]
        det = details.get(eid, {})

        games.append({
            "gameId": eid,
            "statusText": status,
            "homeTeam": {
                "teamName": home["team"]["displayName"],
                "abbreviation": home["team"].get("abbreviation", ""),
                "score": int(home.get("score", 0)),
            },
            "awayTeam": {
                "teamName": away["team"]["displayName"],
                "abbreviation": away["team"].get("abbreviation", ""),
                "score": int(away.get("score", 0)),
            },
            "periods": extract_periods(home, away),
            "events": [],
            "plays": det.get("plays", []),
            "scoringPlays": det.get("scoringPlays", []),
            "drives": det.get("drives", []),
            "stats": det.get("stats", {}),
            "currentDrive": det.get("currentDrive"),
        })
    return games


def fingerprint(games):
    """Create a change-detection fingerprint from current game states."""
    parts = []
    for g in games:
        plays_len = len(g.get("plays", []))
        drives_len = len(g.get("drives", []))
        parts.append(
            f"{g['gameId']}_{g['homeTeam']['score']}_{g['awayTeam']['score']}_{g['statusText']}_{plays_len}_{drives_len}"
        )
    return "|".join(parts)


def display(games):
    """Print a formatted NFL scoreboard summary to the terminal."""
    print("\033c", end="")
    print("=" * 60)
    print(f"{'NFL LIVE SCOREBOARD':^60}")
    print("=" * 60)
    for g in games:
        home = f"{g['homeTeam']['teamName']} ({g['homeTeam']['score']})"
        away = f"{g['awayTeam']['teamName']} ({g['awayTeam']['score']})"
        plays = g.get("plays", [])
        drives = g.get("drives", [])
        print(f"  {away:25} @ {home:25} | {g['statusText']}")
        print(f"    plays={len(plays)} drives={len(drives)} stats={len(g.get('stats', {}))}")
    print("=" * 60)


def start_engine():
    """Main loop: fetch NFL data, fingerprint, publish to Kafka."""
    last_fp = None
    logger.info("Starting NFL producer -> %s via %s", KAFKA_TOPIC, KAFKA_BOOTSTRAP)

    while True:
        try:
            games = fetch_games()
            if games:
                display(games)
                fp = fingerprint(games)
                if fp != last_fp:
                    producer.send(KAFKA_TOPIC, value={"league": "nfl", "games": games})
                    producer.flush()
                    last_fp = fp

            time.sleep(5)
        except Exception as e:
            logger.error("NFL Engine Error: %s", e)
            time.sleep(5)


if __name__ == "__main__":
    start_engine()
