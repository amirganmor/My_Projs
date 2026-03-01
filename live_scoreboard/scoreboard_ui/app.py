"""
Scoreboard Web UI -- Flask app with Kafka consumer.

Consumes live game data from all league Kafka topics and serves
a real-time scoreboard via HTTP polling.
"""

import os
import json
import time
import logging
import threading
from flask import Flask, render_template, jsonify
from kafka import KafkaConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPICS = [
    "nba_scores", "nfl_scores", "premier_league_scores",
    "la_liga_scores", "champions_league_scores",
]

VALID_LEAGUES = {"nba", "nfl", "premier_league", "la_liga", "champions_league"}

app = Flask(__name__)

scores_lock = threading.Lock()
scores = {league: [] for league in VALID_LEAGUES}


def kafka_listener():
    """Background thread: consume Kafka messages and update in-memory scores."""
    backoff = 3
    while True:
        try:
            logger.info("Kafka listener connecting to %s ...", KAFKA_BOOTSTRAP)
            consumer = KafkaConsumer(
                *TOPICS,
                bootstrap_servers=[KAFKA_BOOTSTRAP],
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="earliest",
                group_id=None,
                enable_auto_commit=False,
                metadata_max_age_ms=10000,
                reconnect_backoff_ms=500,
                reconnect_backoff_max_ms=5000,
            )
            logger.info("Kafka listener connected, subscribed to %s", TOPICS)
            backoff = 3
            for message in consumer:
                try:
                    payload = message.value
                except Exception:
                    logger.warning("Failed to decode Kafka message, skipping")
                    continue
                league = payload.get("league")
                games = payload.get("games", [])
                if league and league in VALID_LEAGUES and isinstance(games, list):
                    with scores_lock:
                        scores[league] = games
                    logger.info("Updated %s: %d games", league, len(games))
                else:
                    logger.warning("Ignoring message with unknown league: %s", league)
        except Exception as e:
            logger.error("Kafka consumer error (retrying in %ds): %s", backoff, e)
            time.sleep(backoff)
            backoff = min(backoff * 2, 30)


@app.route("/")
def index():
    """Serve the main scoreboard page."""
    return render_template("index.html")


@app.route("/api/scores")
def api_scores():
    """Return current scores snapshot as JSON."""
    with scores_lock:
        snapshot = {k: list(v) for k, v in scores.items()}
    return jsonify(snapshot)


if __name__ == "__main__":
    t = threading.Thread(target=kafka_listener, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5050, debug=False)
