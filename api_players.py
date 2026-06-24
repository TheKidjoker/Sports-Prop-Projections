# ─── BallDontLie NBA Player Stats ─────────────────────────────────────────────
# Player ID lookups, recent game points, and game logs via balldontlie.io.

import os
import time as _time
import threading
import requests
from api_cache import _cached_request

BASE_URL = "https://api.balldontlie.io/v1"

def _bdl_headers():
    """Return authorization headers for BallDontLie API v2."""
    key = os.environ.get("BALLDONTLIE_API_KEY", "")
    if key:
        return {"Authorization": key}
    return {}

# In-memory cache for player ID lookups (avoids redundant HTTP requests)
_player_id_cache = {}
_player_id_lock = threading.Lock()
_PLAYER_ID_MAX = 500

# Game log cache — longer TTL than general HTTP cache since logs don't change intraday
_game_log_cache = {}
_game_log_lock = threading.Lock()
_GAME_LOG_TTL = 1800  # 30 minutes
_GAME_LOG_MAX = 200


def get_player_id(player_name):
    with _player_id_lock:
        if player_name in _player_id_cache:
            return _player_id_cache[player_name]

    try:
        response = requests.get(
            f"{BASE_URL}/players",
            params={"search": player_name},
            headers=_bdl_headers(),
            timeout=10
        )

        if response.status_code != 200:
            return None

        data = response.json()

        result = None
        if data.get("data"):
            result = data["data"][0]["id"]

        with _player_id_lock:
            if len(_player_id_cache) >= _PLAYER_ID_MAX:
                # Evict oldest ~20% of entries
                keys = list(_player_id_cache.keys())
                for k in keys[:len(keys) // 5]:
                    del _player_id_cache[k]
            _player_id_cache[player_name] = result
        return result
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_recent_game_points(player_id, games=5):
    try:
        response = requests.get(
            f"{BASE_URL}/stats",
            params={
                "player_ids[]": player_id,
                "per_page": games,
                "sort": "-game.date"
            },
            headers=_bdl_headers(),
            timeout=10
        )

        if response.status_code != 200:
            return []

        data = response.json()
        points = []

        for game in data.get("data", []):
            if game.get("min") and game.get("min") != "00":
                points.append(game.get("pts", 0))

        return points
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return []


def get_player_recent_points(player_name, games=5):
    player_id = get_player_id(player_name)

    if not player_id:
        return None

    return get_recent_game_points(player_id, games)


def get_player_game_log(player_name, count=7, sport="nba", athlete_id=None, team_id=None):
    """
    Fetches recent game log with full stat lines.
    NBA uses balldontlie.io; CBB uses ESPN schedule + boxscore.
    Uses a 30-min dedicated cache to avoid re-fetching between prop loads.

    Returns:
        List of dicts: [{pts, reb, ast, min, date}, ...] or None
    """
    if sport in ("cbb", "nhl"):
        from api_client import get_player_game_log_espn
        cache_key = f"{player_name}|{count}|{sport}"
        now = _time.time()
        with _game_log_lock:
            entry = _game_log_cache.get(cache_key)
            if entry and (now - entry["ts"]) < _GAME_LOG_TTL:
                return entry["data"]
        result = get_player_game_log_espn(player_name, athlete_id, team_id, sport, count)
        with _game_log_lock:
            _game_log_cache[cache_key] = {"data": result, "ts": _time.time()}
            # Same eviction bound as the NBA path below — without it this
            # cache grows unbounded across distinct players (memory leak).
            if len(_game_log_cache) > _GAME_LOG_MAX:
                oldest = sorted(_game_log_cache, key=lambda k: _game_log_cache[k]["ts"])
                for old_key in oldest[:len(_game_log_cache) - _GAME_LOG_MAX]:
                    del _game_log_cache[old_key]
        return result

    if sport != "nba":
        return None

    # Check dedicated game log cache first
    cache_key = f"{player_name}|{count}"
    now = _time.time()
    with _game_log_lock:
        entry = _game_log_cache.get(cache_key)
        if entry and (now - entry["ts"]) < _GAME_LOG_TTL:
            return entry["data"]

    player_id = get_player_id(player_name)
    if not player_id:
        return None

    try:
        url = f"{BASE_URL}/stats"
        data = _cached_request(url, params={
            "player_ids[]": player_id,
            "per_page": count,
            "sort": "-game.date",
        }, timeout=10, headers=_bdl_headers())

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

        result = games if games else None

        # Store in dedicated cache
        with _game_log_lock:
            _game_log_cache[cache_key] = {"data": result, "ts": _time.time()}
            if len(_game_log_cache) > _GAME_LOG_MAX:
                oldest = sorted(_game_log_cache, key=lambda k: _game_log_cache[k]["ts"])
                for old_key in oldest[:len(_game_log_cache) - _GAME_LOG_MAX]:
                    del _game_log_cache[old_key]

        return result

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None
