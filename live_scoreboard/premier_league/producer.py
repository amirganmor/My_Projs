"""Premier League producer -- thin wrapper around shared soccer engine."""

from shared.soccer_producer import SoccerEngine

if __name__ == "__main__":
    SoccerEngine(
        kafka_topic="premier_league_scores",
        league_key="premier_league",
        espn_slug="eng.1",
        display_name="PREMIER LEAGUE",
    ).start()
