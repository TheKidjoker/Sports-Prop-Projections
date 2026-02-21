import os
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = "https://www.balldontlie.io/api/v1"

# How many hours after kickoff before a game is considered stale
STALE_HOURS = 2


def is_game_stale(game_date_str):
    """
    Returns True if the game's scheduled start was 2+ hours ago (UTC comparison).
    """
    if not game_date_str:
        return False
    try:
        game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - game_dt >= timedelta(hours=STALE_HOURS)
    except (ValueError, TypeError):
        return False

# ESPN URL builder
SPORT_MAP = {
    "nba": {"category": "basketball", "league": "nba"},
    "nhl": {"category": "hockey", "league": "nhl"},
    "cfb": {"category": "football", "league": "college-football"},
    "nfl": {"category": "football", "league": "nfl"},
    "cbb": {"category": "basketball", "league": "mens-college-basketball"},
}


def _espn_url(sport, endpoint):
    """Build ESPN API URL for a given sport and endpoint."""
    info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
    base = "https://site.api.espn.com/apis/site/v2/sports"
    return f"{base}/{info['category']}/{info['league']}/{endpoint}"


def _espn_player_stats_url(sport, athlete_id):
    """Build ESPN player stats URL."""
    info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
    return (
        f"https://site.web.api.espn.com/apis/common/v3/sports/"
        f"{info['category']}/{info['league']}/athletes/{athlete_id}/stats"
    )


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


def get_todays_games(sport="nba", date_str=None):
    """
    Fetches today's games from the ESPN scoreboard API.

    Args:
        sport: "nba", "nhl", "cfb", or "nfl"
        date_str: Optional YYYYMMDD string to fetch a specific date's games.

    Returns:
        List of dicts: [{event_id, home_team, away_team, game_status, ...}, ...]
        Empty list on failure.
    """
    try:
        url = _espn_url(sport, "scoreboard")
        params = {}
        if date_str:
            params["dates"] = date_str
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return []

        data = response.json()
        games = []

        for event in data.get("events", []):
            event_id = event.get("id")
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])

            home_team = None
            away_team = None
            home_team_id = None
            away_team_id = None
            home_rank = None
            away_rank = None

            for team in competitors:
                team_info = team.get("team", {})
                name = team_info.get("displayName", "")
                tid = team_info.get("id")

                # Extract ranking (curatedRank.current); 99 or 0 = unranked
                rank_val = team.get("curatedRank", {}).get("current", 99)
                rank = rank_val if rank_val not in (0, 99) else None

                if team.get("homeAway") == "home":
                    home_team = name
                    home_team_id = tid
                    home_rank = rank
                else:
                    away_team = name
                    away_team_id = tid
                    away_rank = rank

            game_date = event.get("date", "")

            # Extract game status
            game_status = (
                competition.get("status", {})
                .get("type", {})
                .get("name", "STATUS_SCHEDULED")
            )

            # Extract venue data
            venue_obj = competition.get("venue", {})
            venue_name = venue_obj.get("fullName", "")
            venue_address = venue_obj.get("address", {})
            venue_city = venue_address.get("city", "")
            venue_state = venue_address.get("state", "")

            if event_id and home_team and away_team:
                game_entry = {
                    "event_id": event_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                    "game_date": game_date,
                    "game_status": game_status,
                    "venue_name": venue_name,
                    "venue_city": venue_city,
                    "venue_state": venue_state,
                    "home_rank": home_rank,
                    "away_rank": away_rank,
                }

                # Capture inline weather for NFL from scoreboard
                if sport == "nfl":
                    weather_obj = competition.get("weather", {})
                    if weather_obj:
                        game_entry["weather"] = {
                            "temperature": weather_obj.get("temperature"),
                            "condition": weather_obj.get("displayValue", ""),
                            "wind_speed": weather_obj.get("windSpeed"),
                            "precipitation": weather_obj.get("precipitation"),
                        }

                games.append(game_entry)

        return games

    except (requests.RequestException, KeyError, IndexError):
        return []


def get_game_spread(event_id, sport="nba"):
    """
    Fetches opening and current home team spreads for a given game.

    Args:
        event_id: ESPN event ID
        sport: "nba" or "nhl"

    Returns:
        (opening_spread, current_spread) as floats, or (None, None) on failure
    """
    try:
        url = _espn_url(sport, "summary")
        response = requests.get(
            url,
            params={"event": event_id},
            timeout=10,
        )
        if response.status_code != 200:
            return None, None

        data = response.json()
        pickcenter = data.get("pickcenter", [])

        if not pickcenter:
            return None, None

        point_spread = pickcenter[0].get("pointSpread", {})
        home_spread = point_spread.get("home", {})

        opening = home_spread.get("open", {}).get("line")
        current = home_spread.get("close", {}).get("line")

        if opening is not None and current is not None:
            return float(opening), float(current)

        return None, None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None, None


def find_game_by_team(team_name, sport="nba"):
    """
    Searches today's games for a team name match (case-insensitive substring).

    Args:
        team_name: Team name to search for (e.g., "Lakers", "Los Angeles Lakers")
        sport: "nba" or "nhl"

    Returns:
        event_id if found, None otherwise
    """
    games = get_todays_games(sport)
    search = team_name.strip().lower()

    for game in games:
        if (search in game["home_team"].lower()
                or search in game["away_team"].lower()):
            return game["event_id"]

    return None


def get_all_injuries(sport="nba"):
    """
    Fetches current injuries from ESPN.

    Args:
        sport: "nba" or "nhl"

    Returns:
        Dict mapping team display name -> list of injury dicts.
    """
    try:
        url = _espn_url(sport, "injuries")
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return {}

        data = response.json()
        injuries_by_team = {}

        for team_entry in data.get("injuries", []):
            team_name = team_entry.get("team", {}).get("displayName", "Unknown")
            team_injuries = []

            for item in team_entry.get("injuries", []):
                athlete = item.get("athlete", {})
                player_name = athlete.get("displayName", "")
                player_id = athlete.get("id")
                status = item.get("status", "")
                injury_date = item.get("date", "")
                short_comment = item.get("shortComment", "")

                if player_name:
                    team_injuries.append({
                        "player_name": player_name,
                        "player_id": player_id,
                        "status": status,
                        "injury_date": injury_date,
                        "short_comment": short_comment,
                    })

            if team_injuries:
                injuries_by_team[team_name] = team_injuries

        return injuries_by_team

    except (requests.RequestException, KeyError, IndexError):
        return {}


def get_player_season_averages(athlete_id, sport="nba"):
    """
    Fetches a player's season averages from ESPN.

    Args:
        athlete_id: ESPN athlete ID
        sport: "nba" or "nhl"

    Returns:
        Dict with stat keys or None on failure.
        NBA: {ppg, rpg, apg, mpg}
        NHL: {ptspg, gpg, apg, toi}
    """
    try:
        url = _espn_player_stats_url(sport, athlete_id)
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        categories = data.get("categories", [])

        stats = {}

        if sport == "nfl":
            for category in categories:
                for stat in category.get("stats", []):
                    name = stat.get("name", "")
                    value = stat.get("value")
                    if value is None:
                        continue
                    if name == "passingYardsPerGame":
                        stats["pass_ypg"] = float(value)
                    elif name == "QBRating" or name == "QBR":
                        stats["qbr"] = float(value)
                    elif name == "rushingYardsPerGame":
                        stats["rush_ypg"] = float(value)
                    elif name == "receivingYardsPerGame":
                        stats["rec_ypg"] = float(value)
                    elif name == "totalTouchdowns":
                        stats["total_td"] = float(value)
        elif sport == "nhl":
            for category in categories:
                for stat in category.get("stats", []):
                    name = stat.get("name", "")
                    value = stat.get("value")
                    if value is None:
                        continue
                    if name == "avgPoints":
                        stats["ptspg"] = float(value)
                    elif name == "avgGoals":
                        stats["gpg"] = float(value)
                    elif name == "avgAssists":
                        stats["apg"] = float(value)
                    elif name == "avgTimeOnIce":
                        stats["toi"] = float(value)
        else:
            for category in categories:
                if category.get("name") != "offense":
                    continue
                for stat in category.get("stats", []):
                    name = stat.get("name", "")
                    value = stat.get("value")
                    if value is None:
                        continue
                    if name == "avgPoints":
                        stats["ppg"] = float(value)
                    elif name == "avgRebounds":
                        stats["rpg"] = float(value)
                    elif name == "avgAssists":
                        stats["apg"] = float(value)
                    elif name == "avgMinutes":
                        stats["mpg"] = float(value)

        # Check for primary stat
        if sport == "nfl" and (stats.get("pass_ypg") is not None or stats.get("rush_ypg") is not None):
            return stats
        elif sport == "nhl" and stats.get("ptspg") is not None:
            return stats
        elif sport not in ("nhl", "nfl") and stats.get("ppg") is not None:
            return stats

        return None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_game_overunder(event_id, sport="nfl"):
    """
    Fetches the over/under total from ESPN pickcenter.

    Returns:
        Float total or None on failure.
    """
    try:
        url = _espn_url(sport, "summary")
        response = requests.get(url, params={"event": event_id}, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        pickcenter = data.get("pickcenter", [])
        if not pickcenter:
            return None

        return float(pickcenter[0].get("overUnder", 0)) or None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_team_recent_results(team_id, count=4):
    """
    Fetches last N game results for an NFL team from ESPN.

    Returns:
        List of dicts: [{result: 'W'/'L', score: int, opp_score: int}, ...]
        or empty list on failure.
    """
    try:
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/"
            f"teams/{team_id}/schedule"
        )
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return []

        data = response.json()
        events = data.get("events", [])

        results = []
        for event in reversed(events):
            competitions = event.get("competitions", [{}])
            if not competitions:
                continue
            comp = competitions[0]
            status_type = comp.get("status", {}).get("type", {}).get("name", "")
            if status_type != "STATUS_FINAL":
                continue

            competitors = comp.get("competitors", [])
            team_score = None
            opp_score = None
            for c in competitors:
                if str(c.get("id")) == str(team_id):
                    team_score = int(c.get("score", 0))
                else:
                    opp_score = int(c.get("score", 0))

            if team_score is not None and opp_score is not None:
                results.append({
                    "result": "W" if team_score > opp_score else "L",
                    "score": team_score,
                    "opp_score": opp_score,
                })
                if len(results) >= count:
                    break

        return results

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return []


def get_game_weather_espn(event_id, sport="nfl"):
    """
    Fetches weather data from ESPN game summary (gameInfo.weather).

    Returns:
        Dict with temperature, wind_speed, condition, precipitation or None.
    """
    try:
        url = _espn_url(sport, "summary")
        response = requests.get(url, params={"event": event_id}, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
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


def get_game_final_score(event_id, sport="nba"):
    """
    Fetches final score from ESPN game summary.

    Returns:
        (home_score, away_score, is_final) tuple.
        (None, None, False) on failure or if game not final.
    """
    try:
        url = _espn_url(sport, "summary")
        response = requests.get(url, params={"event": event_id}, timeout=10)
        if response.status_code != 200:
            return None, None, False

        data = response.json()
        header = data.get("header", {})
        competitions = header.get("competitions", [])
        if not competitions:
            return None, None, False

        comp = competitions[0]
        status_name = comp.get("status", {}).get("type", {}).get("name", "")
        is_final = status_name == "STATUS_FINAL"

        if not is_final:
            return None, None, False

        competitors = comp.get("competitors", [])
        home_score = None
        away_score = None
        for c in competitors:
            if c.get("homeAway") == "home":
                home_score = int(c.get("score", 0))
            else:
                away_score = int(c.get("score", 0))

        if home_score is not None and away_score is not None:
            return home_score, away_score, True

        return None, None, False

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None, None, False


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
