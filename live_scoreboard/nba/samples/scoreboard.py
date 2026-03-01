from nba_api.live.nba.endpoints import scoreboard

games = scoreboard.ScoreBoard().games.get_dict()

for game in games:
    print("Game ID:", game['gameId'])
    print("Status:", game['gameStatusText'])
    print("Home:", game['homeTeam']['teamName'], "-", game['homeTeam']['score'])
    print("Away:", game['awayTeam']['teamName'], "-", game['awayTeam']['score'])
    print("--------")
