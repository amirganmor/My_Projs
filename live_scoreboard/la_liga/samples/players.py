import requests

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard"
SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/summary?event={event_id}"

response = requests.get(SCOREBOARD_URL)
data = response.json()

for game in data["events"]:
    event_id = game["id"]
    status = game["status"]["type"]["description"]
    print(f"Game ID: {event_id} | Status: {status}")

    summary = requests.get(SUMMARY_URL.format(event_id=event_id)).json()

    for team_data in summary.get("boxscore", {}).get("players", []):
        team_name = team_data.get("team", {}).get("displayName", "Unknown")
        print(f"\n  {team_name}:")
        for stat_group in team_data.get("statistics", []):
            category = stat_group.get("name", "")
            labels = stat_group.get("labels", [])
            for athlete in stat_group.get("athletes", []):
                name = athlete.get("athlete", {}).get("displayName", "Unknown")
                stats = dict(zip(labels, athlete.get("stats", [])))
                print(f"    {name}: {stats}")

    print("\n------------------------\n")
