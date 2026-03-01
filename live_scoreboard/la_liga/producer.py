"""La Liga producer -- thin wrapper around shared soccer engine."""

from shared.soccer_producer import SoccerEngine

if __name__ == "__main__":
    SoccerEngine(
        kafka_topic="la_liga_scores",
        league_key="la_liga",
        espn_slug="esp.1",
        display_name="LA LIGA",
    ).start()
