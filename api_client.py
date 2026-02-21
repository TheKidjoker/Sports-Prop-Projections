import requests

BASE_URL = "https://www.balldontlie.io/api/v1"


def get_player_id(player_name):
    response = requests.get(
        f"{BASE_URL}/players",
        params={"search": player_name}
    )

    if response.status_code != 200:
        return None

    data = response.json()

    if data["data"]:
        return data["data"][0]["id"]

    return None


def get_recent_game_points(player_id, games=5):
    response = requests.get(
        f"{BASE_URL}/stats",
        params={
            "player_ids[]": player_id,
            "per_page": games,
            "sort": "-game.date"
        }
    )

    if response.status_code != 200:
        return []

    data = response.json()
    points = []

    for game in data["data"]:
        if game["min"] and game["min"] != "00":
            points.append(game["pts"])

    return points


def get_player_recent_points(player_name, games=5):
    player_id = get_player_id(player_name)

    if not player_id:
        return None

    return get_recent_game_points(player_id, games)
