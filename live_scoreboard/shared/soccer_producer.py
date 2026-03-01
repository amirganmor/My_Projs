"""
Shared soccer producer engine used by Premier League, La Liga, and Champions League.

Each league instantiates SoccerEngine with its specific ESPN slug, Kafka topic,
league key, and display name. All data fetching, normalization, caching,
fingerprinting, and Kafka publishing logic lives here.
"""

import logging
import time
import json
import os
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from kafka import KafkaProducer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

SKIP_STATUSES = {"Scheduled", "Postponed", "Canceled", "Unnecessary"}
ENDED_STATUSES = {"Full Time", "Final Score", "Final Score - After Extra Time", "Ended", "Abandoned"}

LIVE_STATUSES = {
    "First Half", "Second Half", "Extra Time",
    "Extra Time First Half", "Extra Time Second Half",
    "Penalty Shootout", "Halftime",
}

STAT_MAP = {
    "possessionPct": "possession", "possession": "possession",
    "totalShots": "shots", "shotsTotal": "shots",
    "shotsOnTarget": "shotsOnTarget", "onTargetShots": "shotsOnTarget",
    "blockedShots": "shotsBlocked",
    "cornerKicks": "corners", "corners": "corners", "wonCorners": "corners",
    "foulsCommitted": "fouls", "fouls": "fouls",
    "offsides": "offsides", "saves": "saves",
    "totalPasses": "passes", "accuratePasses": "accuratePasses", "passPct": "passAccuracy",
    "totalCrosses": "crosses", "accurateCrosses": "accurateCrosses",
    "totalTackles": "tackles", "effectiveTackles": "effectiveTackles",
    "interceptions": "interceptions",
    "totalClearance": "clearances", "effectiveClearance": "clearances",
    "yellowCards": "yellowCards", "redCards": "redCards",
    "totalLongBalls": "longBalls",
}

SUMMARY_TTL_DEFAULT = 30
SUMMARY_TTL_LIVE = 3
MAX_FETCH_WORKERS = 6
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


class SoccerEngine:
    """Fetches live soccer data from ESPN, publishes to Kafka."""

    def __init__(self, kafka_topic, league_key, espn_slug, display_name):
        self.kafka_topic = kafka_topic
        self.league_key = league_key
        self.espn_slug = espn_slug
        self.display_name = display_name
        self.espn_url = f"{ESPN_BASE}/{espn_slug}/scoreboard"
        self.summary_url = f"{ESPN_BASE}/{espn_slug}/summary?event={{event_id}}"

        self.producer = KafkaProducer(
            bootstrap_servers=[KAFKA_BOOTSTRAP],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        self.summary_cache = {}
        self.summary_ts = {}

    def _summary_ttl(self, status):
        """Return cache TTL based on game status."""
        return SUMMARY_TTL_LIVE if status in LIVE_STATUSES else SUMMARY_TTL_DEFAULT

    def fetch_match_details(self, event_id, status):
        """Fetch goals, cards, substitutions, stats, and commentary from ESPN summary."""
        if status in SKIP_STATUSES:
            return [], [], {}, [], []

        now = time.time()
        ttl = self._summary_ttl(status)
        if event_id in self.summary_cache and (now - self.summary_ts.get(event_id, 0)) < ttl:
            return self.summary_cache[event_id]

        try:
            time.sleep(0.15)
            resp = requests.get(self.summary_url.format(event_id=event_id), timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            logger.warning("Summary fetch failed for %s: %s", event_id, e)
            return self.summary_cache.get(event_id, ([], [], {}, [], []))

        events = self._parse_key_events(data)
        periods = self._parse_periods(data)
        stats = self._parse_stats(data, periods)
        commentary = self._parse_commentary(data)
        lineups = self._parse_lineups(data)

        result = (events, periods, stats, commentary, lineups)
        self.summary_cache[event_id] = result
        self.summary_ts[event_id] = now
        return result

    def _parse_key_events(self, data):
        """Extract goal, card, and substitution events from ESPN key events."""
        events = []
        for kev in data.get("keyEvents", []):
            play = kev.get("play", {})
            clock = play.get("clock", {})
            minute = clock.get("displayValue", "")
            minute_int = None
            if minute:
                try:
                    minute_int = int(minute.strip("'").split(":")[0])
                except (ValueError, IndexError):
                    pass

            ptype = play.get("type", {}).get("text", "").lower()
            team_name = play.get("team", {}).get("displayName", "")
            participants = play.get("participants", [])
            player_name = participants[0].get("athlete", {}).get("displayName", "") if participants else ""

            if "goal" in ptype and "own" not in ptype:
                events.append({"type": "goal", "minute": minute_int, "player": player_name, "team": team_name})
            elif "own goal" in ptype:
                events.append({"type": "goal", "minute": minute_int, "player": f"{player_name} (OG)", "team": team_name})
            elif "yellow" in ptype and "red" not in ptype:
                events.append({"type": "yellow_card", "minute": minute_int, "player": player_name, "team": team_name})
            elif "red" in ptype:
                events.append({"type": "red_card", "minute": minute_int, "player": player_name, "team": team_name})
            elif "substitution" in ptype:
                player_in = participants[1].get("athlete", {}).get("displayName", "") if len(participants) > 1 else ""
                events.append({
                    "type": "substitution", "minute": minute_int,
                    "playerIn": player_in, "playerOut": player_name, "team": team_name,
                })
        return events

    def _parse_periods(self, data):
        """Extract period scores from header competitors."""
        competitors = data.get("header", {}).get("competitions", [{}])[0].get("competitors", [])
        home_comp = next((c for c in competitors if c.get("homeAway") == "home"), {})
        away_comp = next((c for c in competitors if c.get("homeAway") == "away"), {})
        periods = []
        for i, (hl, al) in enumerate(zip(home_comp.get("linescores", []), away_comp.get("linescores", []))):
            periods.append({
                "period": i + 1,
                "homeScore": int(hl.get("value", 0)),
                "awayScore": int(al.get("value", 0)),
            })
        return periods

    def _parse_stats(self, data, periods_unused):
        """Extract team comparison stats from boxscore."""
        competitors = data.get("header", {}).get("competitions", [{}])[0].get("competitors", [])
        home_comp = next((c for c in competitors if c.get("homeAway") == "home"), {})

        stats = {}
        boxscore_teams = data.get("boxscore", {}).get("teams", [])
        if len(boxscore_teams) >= 2:
            home_id = home_comp.get("id", "")
            home_box = away_box = None
            for bt in boxscore_teams:
                if bt.get("team", {}).get("id", "") == home_id:
                    home_box = bt
                else:
                    away_box = bt
            if not home_box or not away_box:
                home_box, away_box = boxscore_teams[0], boxscore_teams[1]
            h_st = {s.get("name"): s.get("displayValue", "") for s in home_box.get("statistics", [])}
            a_st = {s.get("name"): s.get("displayValue", "") for s in away_box.get("statistics", [])}
            for api_name, display_name in STAT_MAP.items():
                if display_name not in stats and (api_name in h_st or api_name in a_st):
                    stats[display_name] = [h_st.get(api_name, "0"), a_st.get(api_name, "0")]
        return stats

    def _parse_commentary(self, data):
        """Extract play-by-play commentary with field coordinates."""
        commentary = []
        for item in data.get("commentary", []):
            play_obj = item.get("play") or {}
            entry = {
                "minute": item.get("time", {}).get("displayValue", ""),
                "text": item.get("text", ""),
                "type": play_obj.get("type", {}).get("type", "") if play_obj else "",
                "team": play_obj.get("team", {}).get("displayName", "") if play_obj else "",
            }
            if play_obj:
                for coord_key in ("fieldPositionX", "fieldPositionY",
                                  "fieldPosition2X", "fieldPosition2Y"):
                    val = play_obj.get(coord_key)
                    if val is not None:
                        entry[coord_key] = val
            commentary.append(entry)
        return commentary

    def _parse_lineups(self, data):
        """Extract team rosters and formations."""
        lineups = []
        for roster in data.get("rosters", []):
            team_obj = roster.get("team", {})
            team_data = {
                "team": team_obj.get("displayName", ""),
                "color": f"#{team_obj.get('color', '888888')}",
                "altColor": f"#{team_obj.get('alternateColor', 'ffffff')}",
                "formation": roster.get("formation", ""),
                "homeAway": roster.get("homeAway", ""),
                "players": [],
            }
            for entry in roster.get("roster", []):
                pos_obj = entry.get("position", {})
                team_data["players"].append({
                    "name": entry.get("athlete", {}).get("displayName", ""),
                    "jersey": entry.get("jersey", ""),
                    "position": pos_obj.get("abbreviation", ""),
                    "positionFull": pos_obj.get("displayName", ""),
                    "starter": entry.get("starter", False),
                })
            lineups.append(team_data)
        return lineups

    def fetch_games(self):
        """Fetch all games from ESPN scoreboard and enrich with match details."""
        resp = requests.get(self.espn_url, timeout=15)
        resp.raise_for_status()
        raw_events = resp.json().get("events", [])

        event_data = []
        for event in raw_events:
            competitions = event.get("competitions", [])
            if not competitions:
                continue
            comp = competitions[0]
            competitors = comp.get("competitors", [])
            home = next((t for t in competitors if t.get("homeAway") == "home"), None)
            away = next((t for t in competitors if t.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            status_desc = comp.get("status", {}).get("type", {}).get("description", "")
            display_clock = comp.get("status", {}).get("displayClock", "")
            if display_clock and status_desc not in SKIP_STATUSES and status_desc not in ENDED_STATUSES:
                status_detail = f"{status_desc} \u00b7 {display_clock}"
            else:
                status_detail = status_desc
            event_data.append((event, home, away, status_desc, status_detail, display_clock))

        details_map = {}
        with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as pool:
            futures = {
                pool.submit(self.fetch_match_details, ed[0]["id"], ed[3]): ed[0]["id"]
                for ed in event_data
            }
            for future in as_completed(futures):
                eid = futures[future]
                try:
                    details_map[eid] = future.result()
                except Exception:
                    details_map[eid] = ([], [], {}, [], [])

        games = []
        for event, home, away, status_desc, status_detail, display_clock in event_data:
            match_events, match_periods, match_stats, match_commentary, match_lineups = details_map.get(
                event["id"], ([], [], {}, [], [])
            )
            games.append({
                "gameId": event["id"],
                "statusText": status_detail,
                "clock": display_clock,
                "homeTeam": {
                    "teamName": home["team"]["displayName"],
                    "score": int(home.get("score", 0)),
                },
                "awayTeam": {
                    "teamName": away["team"]["displayName"],
                    "score": int(away.get("score", 0)),
                },
                "periods": match_periods,
                "events": match_events,
                "stats": match_stats,
                "plays": match_commentary,
                "lineups": match_lineups,
            })
        return games

    def fingerprint(self, games):
        """Create a change-detection fingerprint from game states."""
        parts = [
            f"{g['gameId']}_{g['homeTeam']['score']}_{g['awayTeam']['score']}"
            f"_{g['statusText']}_{len(g.get('events', []))}_{len(g.get('plays', []))}"
            for g in games
        ]
        return "|".join(parts)

    def display(self, games):
        """Print a formatted scoreboard summary to the terminal."""
        print("\033c", end="")
        print("=" * 60)
        print(f"{self.display_name + ' LIVE SCOREBOARD':^60}")
        print("=" * 60)
        for g in games:
            home = f"{g['homeTeam']['teamName']} ({g['homeTeam']['score']})"
            away = f"{g['awayTeam']['teamName']} ({g['awayTeam']['score']})"
            clock = f" [{g.get('clock', '')}]" if g.get("clock") else ""
            print(f"  {away:25} @ {home:25} | {g['statusText']}{clock}")
        print("=" * 60)

    def start(self):
        """Main loop: fetch, fingerprint, publish to Kafka."""
        last_fp = None
        logger.info("Starting %s producer -> %s via %s", self.display_name, self.kafka_topic, KAFKA_BOOTSTRAP)

        while True:
            try:
                games = self.fetch_games()
                if games:
                    self.display(games)
                    fp = self.fingerprint(games)
                    if fp != last_fp:
                        self.producer.send(
                            self.kafka_topic,
                            value={"league": self.league_key, "games": games},
                        )
                        self.producer.flush()
                        last_fp = fp
                time.sleep(SUMMARY_TTL_LIVE)
            except Exception as e:
                logger.error("%s Engine Error: %s", self.display_name, e)
                time.sleep(SUMMARY_TTL_LIVE)
