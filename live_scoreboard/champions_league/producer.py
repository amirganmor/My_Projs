"""Champions League producer -- thin wrapper around shared soccer engine."""

from shared.soccer_producer import SoccerEngine

if __name__ == "__main__":
    SoccerEngine(
        kafka_topic="champions_league_scores",
        league_key="champions_league",
        espn_slug="uefa.champions",
        display_name="CHAMPIONS LEAGUE",
    ).start()
