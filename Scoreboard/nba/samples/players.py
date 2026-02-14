from nba_api.live.nba.endpoints import scoreboard, boxscore

# 1. Fetch all games today
games = scoreboard.ScoreBoard().games.get_dict()

# 2. Loop all games
for game in games:
    game_id = game["gameId"]
    status = game["gameStatusText"]

    print(f"Game ID: {game_id} | Status: {status}")

    # 3. Fetch player stats for this game
    bs = boxscore.BoxScore(game_id=game_id).get_dict()
    home = bs["game"]["homeTeam"]
    away = bs["game"]["awayTeam"]

    print(f"\nHome Team: {home['teamName']}")
    for player in home["players"]:
        print(player["name"], player["statistics"])

    print(f"\nAway Team: {away['teamName']}")
    for player in away["players"]:
        print(player["name"], player["statistics"])

    print("\n------------------------\n")
