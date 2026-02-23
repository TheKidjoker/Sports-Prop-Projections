# ─── Odds API & Weather ───────────────────────────────────────────────────────
# The-Odds-API spread comparison, player props, and weather lookups.

import os
import requests
from api_cache import _cached_request, _espn_url

ODDS_API_SPORT_MAP = {
    "nba": "basketball_nba",
    "nhl": "icehockey_nhl",
    "nfl": "americanfootball_nfl",
    "cfb": "americanfootball_ncaaf",
    "cbb": "basketball_ncaab",
}


def get_odds_comparison(sport="nba"):
    """
    Fetches spreads from The-Odds-API for multiple sportsbooks.
    Returns per-game data with Pinnacle (sharp) vs consensus spread.
    Gracefully returns empty list if THE_ODDS_API_KEY is not set.

    Called once per sport per scan (not per game).

    Returns:
        List of dicts: [{home_team, away_team, pinnacle_spread, consensus_spread}, ...]
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
            "markets": "spreads",
            "oddsFormat": "american",
        }
        data = _cached_request(url, params=params, timeout=15)
        if data is None:
            return []

        results = []
        for game in data:
            home_team = game.get("home_team", "")
            away_team = game.get("away_team", "")

            pinnacle_spread = None
            all_spreads = []

            for bookmaker in game.get("bookmakers", []):
                book_key = bookmaker.get("key", "")
                for market in bookmaker.get("markets", []):
                    if market.get("key") != "spreads":
                        continue
                    for outcome in market.get("outcomes", []):
                        if outcome.get("name") == home_team:
                            spread_val = outcome.get("point")
                            if spread_val is not None:
                                all_spreads.append(float(spread_val))
                                if book_key == "pinnacle":
                                    pinnacle_spread = float(spread_val)

            if all_spreads:
                consensus = sum(all_spreads) / len(all_spreads)
                results.append({
                    "home_team": home_team,
                    "away_team": away_team,
                    "pinnacle_spread": pinnacle_spread,
                    "consensus_spread": round(consensus, 1),
                })

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


def get_player_props_odds(sport="nba"):
    """
    Fetches player points props from The-Odds-API.
    Called once per scan (like get_odds_comparison).

    Returns:
        dict: {normalized_name: {"points": line_float}}
        Empty dict if no API key.
    """
    api_key = os.environ.get("THE_ODDS_API_KEY")
    if not api_key:
        return {}

    odds_sport = ODDS_API_SPORT_MAP.get(sport)
    if not odds_sport:
        return {}

    try:
        url = f"https://api.the-odds-api.com/v4/sports/{odds_sport}/odds/"
        params = {
            "apiKey": api_key,
            "regions": "us",
            "markets": "player_points,player_rebounds,player_assists",
            "oddsFormat": "american",
        }
        data = _cached_request(url, params=params, timeout=15)
        if data is None:
            return {}

        # Map market keys to our stat names
        market_to_stat = {
            "player_points": "points",
            "player_rebounds": "rebounds",
            "player_assists": "assists",
        }

        props = {}
        for game in data:
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
