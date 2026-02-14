import requests

# ESPN NFL Scoreboard endpoint (LIVE)
url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

response = requests.get(url)
data = response.json()

games = data["events"]

for game in games:
    competition = game["competitions"][0]
    competitors = competition["competitors"]

    home = next(t for t in competitors if t["homeAway"] == "home")
    away = next(t for t in competitors if t["homeAway"] == "away")

    print("Game ID:", game["id"])
    print("Status:", competition["status"]["type"]["description"])
    print(
        "Home:",
        home["team"]["displayName"],
        "-",
        home.get("score", "0")
    )
    print(
        "Away:",
        away["team"]["displayName"],
        "-",
        away.get("score", "0")
    )
    print("--------")

a = 1
