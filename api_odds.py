# ─── Odds API & Weather ───────────────────────────────────────────────────────
# Primary: odds-api.io (250+ books, free tier)
# Fallback: The-Odds-API (theoddsapi.com)
# Weather lookups remain unchanged.

import os
import logging
import requests
from api_cache import _cached_request, _espn_url
from sport_registry import get_odds_api_sport_map
import api_odds_io

logger = logging.getLogger(__name__)

ODDS_API_SPORT_MAP = get_odds_api_sport_map()

# ─── Prop Market → Stat Mappings ──────────────────────────────────────────────
# Shared between _get_player_props_odds_theodds and _get_player_props_odds_full_theodds.

THEODDS_MARKET_MAP = {
    "nhl": {
        "markets_str": "player_points,player_goals,player_assists,player_shots_on_goal",
        "market_to_stat": {
            "player_points": "points",
            "player_goals": "goals",
            "player_assists": "assists",
            "player_shots_on_goal": "shots_on_goal",
        },
    },
    "mlb": {
        "markets_str": "pitcher_strikeouts,batter_hits,batter_total_bases,batter_home_runs,batter_runs_batted_in",
        "market_to_stat": {
            "pitcher_strikeouts": "strikeouts",
            "batter_hits": "hits",
            "batter_total_bases": "total_bases",
            "batter_home_runs": "home_runs",
            "batter_runs_batted_in": "rbis",
        },
    },
    "_default": {
        "markets_str": "player_points,player_rebounds,player_assists,player_points_rebounds_assists,player_points_rebounds,player_points_assists,player_rebounds_assists",
        "market_to_stat": {
            "player_points": "points",
            "player_rebounds": "rebounds",
            "player_assists": "assists",
            "player_points_rebounds_assists": "points_rebounds_assists",
            "player_points_rebounds": "points_rebounds",
            "player_points_assists": "points_assists",
            "player_rebounds_assists": "rebounds_assists",
        },
    },
}


def _get_theodds_market_config(sport):
    """Get markets_str and market_to_stat for a sport."""
    config = THEODDS_MARKET_MAP.get(sport, THEODDS_MARKET_MAP["_default"])
    return config["markets_str"], config["market_to_stat"]


# ─── Primary/Fallback Wrappers ──────────────────────────────────────────────


def get_odds_comparison(sport="nba"):
    """Try odds-api.io first, fall back to The Odds API."""
    if api_odds_io.is_available():
        try:
            result = api_odds_io.get_odds_comparison_io(sport)
            if result:
                logger.debug("[odds] Using odds-api.io for %s spreads (%d games)", sport, len(result))
                return result
        except Exception as e:
            logger.warning("[odds] odds-api.io failed for %s: %s", sport, e)
    return _get_odds_comparison_theodds(sport)


def get_player_props_odds(sport="nba"):
    """Try odds-api.io first, fall back to The Odds API.
    Note: odds-api.io doesn't support player props, so this always falls back."""
    if api_odds_io.is_available():
        try:
            result = api_odds_io.get_player_props_odds_io(sport)
            if result:
                return result
        except Exception:
            pass
    return _get_player_props_odds_theodds(sport)


def get_player_props_odds_full(sport="nba"):
    """Try odds-api.io first, fall back to The Odds API.
    Note: odds-api.io doesn't support player props, so this always falls back."""
    if api_odds_io.is_available():
        try:
            result = api_odds_io.get_player_props_odds_full_io(sport)
            if result:
                return result
        except Exception:
            pass
    return _get_player_props_odds_full_theodds(sport)


def get_multibook_lines(sport="nba"):
    """Try odds-api.io first, fall back to The Odds API."""
    if api_odds_io.is_available():
        try:
            result = api_odds_io.get_multibook_lines_io(sport)
            if result:
                logger.debug("[odds] Using odds-api.io for %s line shop (%d games)", sport, len(result))
                return result
        except Exception as e:
            logger.warning("[odds] odds-api.io line shop failed for %s: %s", sport, e)
    return _get_multibook_lines_theodds(sport)


# ─── The Odds API (Fallback) ────────────────────────────────────────────────


def _get_odds_comparison_theodds(sport="nba"):
    """
    Fetches spreads and totals from The-Odds-API for multiple sportsbooks.
    Returns per-game data with Pinnacle (sharp) vs consensus spread + totals.
    Gracefully returns empty list if THE_ODDS_API_KEY is not set.
    """
    api_key = os.environ.get("THE_ODDS_API_KEY")
    if not api_key:
        return []

    odds_sport = ODDS_API_SPORT_MAP.get(sport)
    if not odds_sport:
        return []

    try:
        url = f"https://api.the-odds-api.com/v4/sports/{odds_sport}/odds/"
        # MLB uses moneyline (h2h) instead of spreads
        markets = "h2h,totals" if sport == "mlb" else "spreads,totals"
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": markets,
            "oddsFormat": "american",
        }
        data = _cached_request(url, params=params, timeout=15)
        if data is None:
            return []
        if not isinstance(data, list):
            print(f"[odds_api] Unexpected response shape for {sport}: {type(data).__name__}", flush=True)
            return []

        results = []
        for game in data:
            if not isinstance(game, dict):
                continue
            home_team = game.get("home_team", "")
            away_team = game.get("away_team", "")

            pinnacle_spread = None
            all_spreads = []
            pinnacle_total = None
            all_totals = []

            for bookmaker in game.get("bookmakers", []):
                book_key = bookmaker.get("key", "")
                for market in bookmaker.get("markets", []):
                    mkey = market.get("key")

                    if mkey == "spreads":
                        for outcome in market.get("outcomes", []):
                            if outcome.get("name") == home_team:
                                spread_val = outcome.get("point")
                                if spread_val is not None:
                                    all_spreads.append(float(spread_val))
                                    if book_key == "pinnacle":
                                        pinnacle_spread = float(spread_val)

                    elif mkey == "totals":
                        for outcome in market.get("outcomes", []):
                            total_val = outcome.get("point")
                            if total_val is not None:
                                all_totals.append(float(total_val))
                                if book_key == "pinnacle":
                                    pinnacle_total = float(total_val)
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
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return []


def _match_odds_to_game(odds_data, home_team, away_team):
    """
    Fuzzy-matches odds data to an ESPN game using team name substrings.

    Returns:
        Matching odds dict or None.
    """
    home_lower = home_team.lower()
    away_lower = away_team.lower()

    for od in odds_data:
        od_home = od["home_team"].lower()
        od_away = od["away_team"].lower()

        # Check substring matches in both directions
        home_match = (
            home_lower in od_home or od_home in home_lower
            or any(w in od_home for w in home_lower.split() if len(w) > 3)
        )
        away_match = (
            away_lower in od_away or od_away in away_lower
            or any(w in od_away for w in away_lower.split() if len(w) > 3)
        )

        if home_match and away_match:
            return od

    return None


def _get_player_props_odds_theodds(sport="nba"):
    """
    Fetches player points props from The-Odds-API.
    """
    api_key = os.environ.get("THE_ODDS_API_KEY")
    if not api_key:
        return {}

    odds_sport = ODDS_API_SPORT_MAP.get(sport)
    if not odds_sport:
        return {}

    try:
        url = f"https://api.the-odds-api.com/v4/sports/{odds_sport}/odds/"

        markets_str, market_to_stat = _get_theodds_market_config(sport)

        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": markets_str,
            "oddsFormat": "american",
        }
        data = _cached_request(url, params=params, timeout=15)
        if data is None:
            return {}

        if not isinstance(data, list):
            print(f"[odds_api] Unexpected props response shape: {type(data).__name__}", flush=True)
            return {}
        props = {}
        for game in data:
            if not isinstance(game, dict):
                continue
            for bookmaker in game.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    stat_name = market_to_stat.get(market.get("key"))
                    if not stat_name:
                        continue
                    for outcome in market.get("outcomes", []):
                        name = outcome.get("description", "")
                        point = outcome.get("point")
                        if name and point is not None:
                            norm = name.strip().lower()
                            if norm not in props:
                                props[norm] = {}
                            if stat_name not in props[norm]:
                                props[norm][stat_name] = float(point)
        return props

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return {}


def _get_player_props_odds_full_theodds(sport="nba"):
    """
    Fetches player prop lines WITH odds from The-Odds-API.
    """
    api_key = os.environ.get("THE_ODDS_API_KEY")
    if not api_key:
        return {}

    odds_sport = ODDS_API_SPORT_MAP.get(sport)
    if not odds_sport:
        return {}

    try:
        url = f"https://api.the-odds-api.com/v4/sports/{odds_sport}/odds/"

        markets_str, market_to_stat = _get_theodds_market_config(sport)

        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": markets_str,
            "oddsFormat": "american",
        }
        data = _cached_request(url, params=params, timeout=15)
        if data is None:
            return {}

        # Collect all odds per player/stat, keep best odds per side
        if not isinstance(data, list):
            print(f"[odds_api] Unexpected props response shape: {type(data).__name__}", flush=True)
            return {}
        props = {}
        for game in data:
            if not isinstance(game, dict):
                continue
            for bookmaker in game.get("bookmakers", []):
                book_key = bookmaker.get("key", "")
                for market in bookmaker.get("markets", []):
                    stat_name = market_to_stat.get(market.get("key"))
                    if not stat_name:
                        continue

                    # Group outcomes by player (description)
                    player_outcomes = {}
                    for outcome in market.get("outcomes", []):
                        name = outcome.get("description", "")
                        if not name:
                            continue
                        norm = name.strip().lower()
                        if norm not in player_outcomes:
                            player_outcomes[norm] = {}
                        side = outcome.get("name", "").lower()  # "over" or "under"
                        player_outcomes[norm][side] = {
                            "point": outcome.get("point"),
                            "price": outcome.get("price"),
                        }

                    for norm, sides in player_outcomes.items():
                        over_data = sides.get("over", {})
                        under_data = sides.get("under", {})

                        line = over_data.get("point") or under_data.get("point")
                        over_price = over_data.get("price")
                        under_price = under_data.get("price")

                        if line is None:
                            continue

                        if norm not in props:
                            props[norm] = {}

                        existing = props[norm].get(stat_name)
                        if existing is None:
                            props[norm][stat_name] = {
                                "line": float(line),
                                "over_odds": over_price,
                                "under_odds": under_price,
                                "bookmaker": book_key,
                            }
                        else:
                            # Keep best over odds (highest/least negative)
                            if over_price is not None:
                                cur_over = existing.get("over_odds")
                                if cur_over is None or over_price > cur_over:
                                    existing["over_odds"] = over_price
                            # Keep best under odds (highest/least negative)
                            if under_price is not None:
                                cur_under = existing.get("under_odds")
                                if cur_under is None or under_price > cur_under:
                                    existing["under_odds"] = under_price

        return props

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return {}


def get_game_weather_espn(event_id, sport="nfl"):
    """
    Fetches weather data from ESPN game summary (gameInfo.weather).

    Returns:
        Dict with temperature, wind_speed, condition, precipitation or None.
    """
    try:
        url = _espn_url(sport, "summary")
        data = _cached_request(url, params={"event": event_id}, timeout=10)
        if data is None:
            return None

        weather = data.get("gameInfo", {}).get("weather", {})
        if not weather:
            return None

        return {
            "temperature": weather.get("temperature"),
            "wind_speed": weather.get("windSpeed"),
            "condition": weather.get("displayValue", ""),
            "precipitation": weather.get("precipitation"),
        }

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_game_weather_openweather(city, state):
    """
    Fallback weather fetch using OpenWeatherMap free tier.
    Requires OPENWEATHER_API_KEY env var.

    Returns:
        Dict with temperature, wind_speed, condition, precipitation or None.
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        return None

    try:
        query = f"{city},{state},US"
        url = "https://api.openweathermap.org/data/2.5/weather"
        response = requests.get(
            url,
            params={"q": query, "appid": api_key, "units": "imperial"},
            timeout=10,
        )
        if response.status_code != 200:
            return None

        data = response.json()
        main = data.get("main", {})
        wind = data.get("wind", {})
        weather_list = data.get("weather", [{}])
        condition = weather_list[0].get("main", "") if weather_list else ""

        rain = data.get("rain", {}).get("1h", 0)
        snow = data.get("snow", {}).get("1h", 0)
        precipitation = rain + snow

        return {
            "temperature": main.get("temp"),
            "wind_speed": wind.get("speed"),
            "condition": condition,
            "precipitation": precipitation if precipitation > 0 else 0,
        }

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def _get_multibook_lines_theodds(sport="nba"):
    """
    Fetch per-book spreads and totals for all games from The-Odds-API.
    """
    api_key = os.environ.get("THE_ODDS_API_KEY")
    if not api_key:
        return []

    odds_sport = ODDS_API_SPORT_MAP.get(sport)
    if not odds_sport:
        return []

    try:
        url = f"https://api.the-odds-api.com/v4/sports/{odds_sport}/odds/"
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": "spreads,totals",
            "oddsFormat": "american",
        }
        data = _cached_request(url, params=params, timeout=15)
        if data is None:
            return []
        if not isinstance(data, list):
            print(f"[odds_api] Unexpected response shape: {type(data).__name__}", flush=True)
            return []

        results = []
        for game in data:
            if not isinstance(game, dict):
                continue
            home_team = game.get("home_team", "")
            away_team = game.get("away_team", "")
            commence_time = game.get("commence_time", "")

            books = {}
            for bookmaker in game.get("bookmakers", []):
                book_key = bookmaker.get("key", "")
                book_title = bookmaker.get("title", book_key)
                book_entry = {}

                for market in bookmaker.get("markets", []):
                    mkey = market.get("key")
                    outcomes = market.get("outcomes", [])

                    if mkey == "spreads":
                        for outcome in outcomes:
                            if outcome.get("name") == home_team:
                                book_entry["spread"] = outcome.get("point")
                                book_entry["spread_odds"] = outcome.get("price")

                    elif mkey == "totals":
                        for outcome in outcomes:
                            point = outcome.get("point")
                            price = outcome.get("price")
                            if outcome.get("name") == "Over":
                                book_entry["total"] = point
                                book_entry["over_odds"] = price
                            elif outcome.get("name") == "Under":
                                book_entry["under_odds"] = price
                                if "total" not in book_entry:
                                    book_entry["total"] = point

                if book_entry:
                    books[book_title] = book_entry

            if not books:
                continue

            # Find best lines
            best_spread = None
            best_total_over = None
            best_total_under = None

            for bk, entry in books.items():
                # Best spread = highest (most favorable to dog)
                if entry.get("spread") is not None:
                    if best_spread is None or entry["spread"] > best_spread["value"]:
                        best_spread = {"book": bk, "value": entry["spread"]}

                # Best over = lowest total (easier to go over)
                if entry.get("total") is not None and entry.get("over_odds") is not None:
                    if best_total_over is None or entry["total"] < best_total_over["total"]:
                        best_total_over = {"book": bk, "total": entry["total"], "odds": entry["over_odds"]}

                # Best under = highest total (easier to go under)
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

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return []
