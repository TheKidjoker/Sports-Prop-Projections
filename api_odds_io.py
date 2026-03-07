# ─── odds-api.io Client ──────────────────────────────────────────────────────
# Primary odds source with 250+ bookmakers. Falls back to The Odds API when
# unavailable. Provides the same function interfaces as api_odds.py.

import os
import time
import logging
import requests
from api_cache import _cached_request

logger = logging.getLogger(__name__)

# ─── Sport / League Mapping ──────────────────────────────────────────────────
# odds-api.io uses sport slug + league slug (discovered via /sports + /leagues)
ODDS_IO_SPORT_MAP = {
    "nba": {"sport": "basketball", "league": "nba"},
    "nhl": {"sport": "ice-hockey", "league": "nhl"},
    "nfl": {"sport": "american-football", "league": "nfl"},
    "cfb": {"sport": "american-football", "league": "ncaaf"},
    "cbb": {"sport": "basketball", "league": "ncaab"},
}

BASE_URL = "https://api.odds-api.io/v3"

# Bookmakers to query (sharp + major US books for consensus)
TARGET_BOOKMAKERS = [
    "Pinnacle", "DraftKings", "FanDuel", "BetMGM", "Caesars",
    "BetRivers", "PointsBet", "Bet365", "Bovada", "WynnBET",
]

# Rate limit tracking
_rate_limit = {"remaining": None, "reset": None}

# ─── Helpers ─────────────────────────────────────────────────────────────────


def _get_api_key():
    return os.environ.get("ODDS_API_IO_KEY", "")


def _decimal_to_american(decimal_odds):
    """Convert decimal odds to American odds."""
    try:
        d = float(decimal_odds)
        if d >= 2.0:
            return round((d - 1) * 100)
        elif d > 1.0:
            return round(-100 / (d - 1))
        else:
            return None
    except (ValueError, TypeError, ZeroDivisionError):
        return None


def _odds_io_request(endpoint, params=None):
    """
    Core HTTP handler for odds-api.io.
    Adds apiKey, tracks rate limit headers, uses shared cache.
    Returns parsed JSON or None.
    """
    api_key = _get_api_key()
    if not api_key:
        return None

    url = f"{BASE_URL}{endpoint}"
    if params is None:
        params = {}
    params["apiKey"] = api_key

    try:
        response = requests.get(url, params=params, timeout=15)

        # Track rate limit headers
        remaining = response.headers.get("x-ratelimit-remaining")
        reset = response.headers.get("x-ratelimit-reset")
        if remaining is not None:
            try:
                _rate_limit["remaining"] = int(remaining)
            except ValueError:
                pass
        if reset is not None:
            _rate_limit["reset"] = reset

        if response.status_code != 200:
            logger.warning("[odds-api.io] %s returned %d", endpoint, response.status_code)
            return None

        return response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("[odds-api.io] Request failed: %s", e)
        return None


def is_available():
    """Check if odds-api.io is available (API key set and rate limit OK)."""
    if not _get_api_key():
        return False
    remaining = _rate_limit.get("remaining")
    if remaining is not None and remaining <= 5:
        return False
    return True


def get_rate_limit_status():
    """Return current rate limit info."""
    return {
        "remaining": _rate_limit.get("remaining"),
        "reset_time": _rate_limit.get("reset"),
        "has_key": bool(_get_api_key()),
    }


# ─── Events ──────────────────────────────────────────────────────────────────


def _get_events(sport="nba"):
    """Fetch today's events for a sport. Returns list of event dicts."""
    mapping = ODDS_IO_SPORT_MAP.get(sport)
    if not mapping:
        return []

    data = _odds_io_request("/events", {
        "sport": mapping["sport"],
        "league": mapping["league"],
        "status": "pending",
        "limit": 50,
    })
    return data if isinstance(data, list) else []


# ─── Odds Comparison (Spreads + Totals) ──────────────────────────────────────


def get_odds_comparison_io(sport="nba"):
    """
    Fetches spreads and totals from odds-api.io for multiple sportsbooks.
    Returns same format as api_odds.get_odds_comparison():
        [{home_team, away_team, pinnacle_spread, consensus_spread,
          pinnacle_total, consensus_total}, ...]
    """
    if not is_available():
        return []

    try:
        events = _get_events(sport)
        if not events:
            return []

        # Batch odds requests (max 10 events per call)
        results = []
        for i in range(0, len(events), 10):
            batch = events[i:i + 10]
            event_ids = ",".join(str(e["id"]) for e in batch)
            bookmakers_str = ",".join(TARGET_BOOKMAKERS)

            odds_data = _odds_io_request("/odds/multi", {
                "eventIds": event_ids,
                "bookmakers": bookmakers_str,
            })
            if not odds_data or not isinstance(odds_data, list):
                continue

            for event_odds in odds_data:
                home_team = event_odds.get("home", "")
                away_team = event_odds.get("away", "")
                bookmakers = event_odds.get("bookmakers", {})

                pinnacle_spread = None
                all_spreads = []
                pinnacle_total = None
                all_totals = []

                for book_name, markets in bookmakers.items():
                    if not isinstance(markets, list):
                        continue
                    is_pinnacle = book_name.lower() == "pinnacle"

                    for market in markets:
                        market_name = (market.get("name") or "").lower()
                        odds_list = market.get("odds", [])

                        if market_name in ("asian handicap", "spread", "spreads"):
                            for odd in odds_list:
                                hdp = odd.get("hdp")
                                if hdp is not None:
                                    # hdp is typically the home handicap
                                    spread_val = float(hdp)
                                    all_spreads.append(spread_val)
                                    if is_pinnacle:
                                        pinnacle_spread = spread_val

                        elif market_name in ("totals", "over/under", "total"):
                            for odd in odds_list:
                                hdp = odd.get("hdp")
                                over = odd.get("over")
                                if hdp is not None:
                                    total_val = float(hdp)
                                    all_totals.append(total_val)
                                    if is_pinnacle:
                                        pinnacle_total = total_val
                                    break  # Only need point once per book

                if all_spreads:
                    consensus = sum(all_spreads) / len(all_spreads)
                    entry = {
                        "home_team": home_team,
                        "away_team": away_team,
                        "pinnacle_spread": pinnacle_spread,
                        "consensus_spread": round(consensus, 1),
                    }
                    if all_totals:
                        entry["pinnacle_total"] = pinnacle_total
                        entry["consensus_total"] = round(sum(all_totals) / len(all_totals), 1)
                    results.append(entry)

        return results

    except (KeyError, IndexError, ValueError, TypeError) as e:
        logger.warning("[odds-api.io] get_odds_comparison failed: %s", e)
        return []


# ─── Player Props ────────────────────────────────────────────────────────────
# odds-api.io does NOT support player props markets. These functions always
# return empty and will fall back to The Odds API automatically.


def get_player_props_odds_io(sport="nba"):
    """Not supported by odds-api.io — always returns empty."""
    return {}


def get_player_props_odds_full_io(sport="nba"):
    """Not supported by odds-api.io — always returns empty."""
    return {}


# ─── Multi-Book Line Shop ───────────────────────────────────────────────────


def get_multibook_lines_io(sport="nba"):
    """
    Fetch per-book spreads and totals for all games from odds-api.io.
    Returns same format as api_odds.get_multibook_lines().
    """
    if not is_available():
        return []

    try:
        events = _get_events(sport)
        if not events:
            return []

        results = []
        for i in range(0, len(events), 10):
            batch = events[i:i + 10]
            event_ids = ",".join(str(e["id"]) for e in batch)
            bookmakers_str = ",".join(TARGET_BOOKMAKERS)

            odds_data = _odds_io_request("/odds/multi", {
                "eventIds": event_ids,
                "bookmakers": bookmakers_str,
            })
            if not odds_data or not isinstance(odds_data, list):
                continue

            for event_odds in odds_data:
                home_team = event_odds.get("home", "")
                away_team = event_odds.get("away", "")
                commence_time = event_odds.get("date", "")
                bookmakers_data = event_odds.get("bookmakers", {})

                books = {}
                for book_name, markets in bookmakers_data.items():
                    if not isinstance(markets, list):
                        continue
                    book_entry = {}

                    for market in markets:
                        market_name = (market.get("name") or "").lower()
                        odds_list = market.get("odds", [])

                        if market_name in ("asian handicap", "spread", "spreads"):
                            for odd in odds_list:
                                hdp = odd.get("hdp")
                                home_dec = odd.get("home")
                                if hdp is not None:
                                    book_entry["spread"] = float(hdp)
                                    if home_dec:
                                        book_entry["spread_odds"] = _decimal_to_american(home_dec)

                        elif market_name in ("totals", "over/under", "total"):
                            for odd in odds_list:
                                hdp = odd.get("hdp")
                                over_dec = odd.get("over")
                                under_dec = odd.get("under")
                                if hdp is not None:
                                    book_entry["total"] = float(hdp)
                                    if over_dec:
                                        book_entry["over_odds"] = _decimal_to_american(over_dec)
                                    if under_dec:
                                        book_entry["under_odds"] = _decimal_to_american(under_dec)
                                    break

                    if book_entry:
                        books[book_name] = book_entry

                if not books:
                    continue

                # Find best lines
                best_spread = None
                best_total_over = None
                best_total_under = None

                for bk, entry in books.items():
                    if entry.get("spread") is not None:
                        if best_spread is None or entry["spread"] > best_spread["value"]:
                            best_spread = {"book": bk, "value": entry["spread"]}
                    if entry.get("total") is not None and entry.get("over_odds") is not None:
                        if best_total_over is None or entry["total"] < best_total_over["total"]:
                            best_total_over = {"book": bk, "total": entry["total"], "odds": entry["over_odds"]}
                    if entry.get("total") is not None and entry.get("under_odds") is not None:
                        if best_total_under is None or entry["total"] > best_total_under["total"]:
                            best_total_under = {"book": bk, "total": entry["total"], "odds": entry["under_odds"]}

                results.append({
                    "home_team": home_team,
                    "away_team": away_team,
                    "commence_time": commence_time,
                    "books": books,
                    "best_spread": best_spread,
                    "best_total_over": best_total_over,
                    "best_total_under": best_total_under,
                })

        return results

    except (KeyError, IndexError, ValueError, TypeError) as e:
        logger.warning("[odds-api.io] get_multibook_lines failed: %s", e)
        return []
