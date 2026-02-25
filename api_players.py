# ─── BallDontLie NBA Player Stats ─────────────────────────────────────────────
# Player ID lookups, recent game points, and game logs via balldontlie.io.

import threading
import requests
from api_cache import _cached_request

BASE_URL = "https://www.balldontlie.io/api/v1"

# In-memory cache for player ID lookups (avoids redundant HTTP requests)
_player_id_cache = {}
_player_id_lock = threading.Lock()


def get_player_id(player_name):
    with _player_id_lock:
        if player_name in _player_id_cache:
            return _player_id_cache[player_name]

    response = requests.get(
        f"{BASE_URL}/players",
        params={"search": player_name}
    )

    if response.status_code != 200:
        return None

    data = response.json()

    result = None
    if data["data"]:
        result = data["data"][0]["id"]

    with _player_id_lock:
        _player_id_cache[player_name] = result
    return result


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


def get_player_game_log(player_name, count=7, sport="nba"):
    """
    Fetches recent game log with full stat lines via balldontlie.io.
    NBA only — returns None for other sports.

    Returns:
        List of dicts: [{pts, reb, ast, min, date}, ...] or None
    """
    if sport != "nba":
        return None

    player_id = get_player_id(player_name)
    if not player_id:
        return None

    try:
        url = f"{BASE_URL}/stats"
        data = _cached_request(url, params={
            "player_ids[]": player_id,
            "per_page": count,
            "sort": "-game.date",
        }, timeout=10)

        if data is None:
            return None

        games = []
        for game in data.get("data", []):
            min_str = game.get("min", "0")
            if not min_str or min_str == "00":
                continue

            # Parse minutes from "35:42" or "35" format
            try:
                if ":" in str(min_str):
                    minutes = int(str(min_str).split(":")[0])
                else:
                    minutes = int(min_str)
            except (ValueError, TypeError):
                minutes = 0

            game_date = ""
            game_obj = game.get("game", {})
            if game_obj:
                game_date = game_obj.get("date", "")

            games.append({
                "pts": game.get("pts", 0),
                "reb": game.get("reb", 0),
                "ast": game.get("ast", 0),
                "min": minutes,
                "date": game_date,
            })

        return games if games else None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None
