# ─── Shared HTTP Caching & ESPN URL Builders ─────────────────────────────────
# Extracted so api_client, api_players, and api_odds can all import without cycles.

import time
import threading
import logging
import requests

logger = logging.getLogger(__name__)

# ─── TTL Response Cache ─────────────────────────────────────────────────────
CACHE_TTL = 600        # 10 minutes for free APIs (ESPN, etc.)
ODDS_API_TTL = 14400   # 4 hours for The Odds API (500 calls/month budget)
CACHE_MAX_SIZE = 200
_cache = {}
_cache_lock = threading.Lock()


def _cached_request(url, params=None, timeout=10, headers=None):
    """
    Thread-safe cached HTTP GET. Returns parsed JSON or None.
    Cache key = URL + sorted query params.
    Uses 4-hour TTL for Odds API, 10-minute TTL for free APIs.
    Checks daily budget before making paid API calls.
    """
    key = url + "|" + str(sorted((params or {}).items()))
    now = time.time()

    is_paid = "the-odds-api.com" in url
    ttl = ODDS_API_TTL if is_paid else CACHE_TTL

    with _cache_lock:
        entry = _cache.get(key)
        if entry and (now - entry["ts"]) < ttl:
            return entry["data"]

    # Check budget before making paid API calls
    if is_paid:
        import api_budget
        if not api_budget.check_budget():
            logger.warning("[cache] Odds API daily budget exhausted — returning None")
            return None

    try:
        response = requests.get(url, params=params, timeout=timeout, headers=headers)
        if response.status_code != 200:
            logger.warning("[cache] %s returned HTTP %s", url, response.status_code)
            return None
        data = response.json()
    except requests.Timeout:
        logger.warning("[cache] Timeout after %ss fetching %s", timeout, url)
        return None
    except requests.RequestException as e:
        logger.warning("[cache] Request failed for %s: %s", url, e)
        return None
    except ValueError as e:
        # 200 OK but body was not valid JSON (HTML error page, empty body, ...)
        logger.warning("[cache] Invalid JSON from %s: %s", url, e)
        return None

    # Record the call for budget tracking
    if is_paid:
        import api_budget
        api_budget.record_call()

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


# ESPN URL builder — mapping sourced from sport_registry
from sport_registry import get_espn_sport_map
SPORT_MAP = get_espn_sport_map()


def _espn_url(sport, endpoint):
    """Build ESPN API URL for a given sport and endpoint."""
    info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
    base = "https://site.api.espn.com/apis/site/v2/sports"
    return f"{base}/{info['category']}/{info['league']}/{endpoint}"
