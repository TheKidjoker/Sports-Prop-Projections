# ─── Shared HTTP Caching & ESPN URL Builders ─────────────────────────────────
# Extracted so api_client, api_players, and api_odds can all import without cycles.

import time
import threading
import requests

# ─── TTL Response Cache ─────────────────────────────────────────────────────
CACHE_TTL = 900  # 15 minutes — ESPN data barely changes; reduces re-fetches during scans
CACHE_MAX_SIZE = 500  # 5 sports × 100+ endpoints; prevents thrashing during hourly cycles
_cache = {}
_cache_lock = threading.Lock()


def _cached_request(url, params=None, timeout=10, headers=None):
    """
    Thread-safe cached HTTP GET. Returns parsed JSON or None.
    Cache key = URL + sorted query params. TTL = CACHE_TTL seconds.
    """
    key = url + "|" + str(sorted((params or {}).items()))
    now = time.time()

    with _cache_lock:
        entry = _cache.get(key)
        if entry and (now - entry["ts"]) < CACHE_TTL:
            return entry["data"]

    try:
        response = requests.get(url, params=params, timeout=timeout, headers=headers)
        if response.status_code != 200:
            return None
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}
        # Evict oldest entries if cache too large
        if len(_cache) > CACHE_MAX_SIZE:
            oldest = sorted(_cache, key=lambda k: _cache[k]["ts"])
            for old_key in oldest[:len(_cache) - CACHE_MAX_SIZE]:
                del _cache[old_key]

    return data


def clear_cache():
    """Flush all cached responses. Useful during long-running collection."""
    with _cache_lock:
        _cache.clear()


# ESPN URL builder
SPORT_MAP = {
    "nba": {"category": "basketball", "league": "nba"},
    "nhl": {"category": "hockey", "league": "nhl"},
    "cfb": {"category": "football", "league": "college-football"},
    "nfl": {"category": "football", "league": "nfl"},
    "cbb": {"category": "basketball", "league": "mens-college-basketball"},
    "mlb": {"category": "baseball", "league": "mlb"},
}


def _espn_url(sport, endpoint):
    """Build ESPN API URL for a given sport and endpoint."""
    info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
    base = "https://site.api.espn.com/apis/site/v2/sports"
    return f"{base}/{info['category']}/{info['league']}/{endpoint}"
