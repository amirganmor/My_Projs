import time
import json
import os
from kafka import KafkaProducer
from nba_api.live.nba.endpoints import scoreboard

class BoxScoreUI:
    """Simulates a real-time UI by formatting the console output"""
    @staticmethod
    def display(games):
        os.system('clear' if os.name == 'posix' else 'cls') 
        print("="*50)
        print(f"{'NBA LIVE SCOREBOARD':^50}")
        print("="*50)
        for game in games:
            home = f"{game['homeTeam']['teamName']} ({game['homeTeam']['score']})"
            away = f"{game['awayTeam']['teamName']} ({game['awayTeam']['score']})"
            status = game['gameStatusText']
            print(f"{away:20} @ {home:20} | {status}")
        print("="*50)

# Initialize Kafka
producer = KafkaProducer(
    bootstrap_servers=['localhost:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def get_board_fingerprint(games_list):
    """
    Creates a unique string based on game IDs and scores.
    Since games_list is a list, we iterate through it directly.
    """
    fingerprint = []
    for game in games_list:
        summary = f"{game['gameId']}_{game['homeTeam']['score']}_{game['awayTeam']['score']}_{game['gameStatusText']}"
        fingerprint.append(summary)
    return "|".join(fingerprint)

def start_engine():
    ui = BoxScoreUI()
    last_fingerprint = None
    
    print("Starting NBA Engine...")
    
    while True:
        try:
            # .games.get_dict() returns a LIST of games
            games = scoreboard.ScoreBoard().games.get_dict()
            
            if games:
                # 1. UI FEED: Pass the list directly
                ui.display(games)
                
                # 2. KAFKA FEED: Check for changes
                current_fingerprint = get_board_fingerprint(games)
                
                if current_fingerprint != last_fingerprint:
                    # We wrap the list in a dict for the Kafka message 
                    # so Spark's schema (which expects a "games" field) works.
                    kafka_payload = {"games": games}
                    producer.send("nba_scoreboard", value=kafka_payload)
                    last_fingerprint = current_fingerprint
                
            # Changed back to 10 seconds for real-time updates
            time.sleep(100) 
        except Exception as e:
            print(f"Engine Error: {e}")
            time.sleep(50)
if __name__ == "__main__":
    start_engine()
