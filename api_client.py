import requests

BASE_URL = "https://www.balldontlie.io/api/v1"
ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
ESPN_INJURIES_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
ESPN_PLAYER_STATS_URL = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{}/stats"


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


def get_todays_games():
    """
    Fetches today's NBA games from the ESPN scoreboard API.

    Returns:
        List of dicts: [{event_id, home_team, away_team}, ...]
        Empty list on failure.
    """
    try:
        response = requests.get(ESPN_SCOREBOARD_URL, timeout=10)
        if response.status_code != 200:
            return []

        data = response.json()
        games = []

        for event in data.get("events", []):
            event_id = event.get("id")
            competitors = event.get("competitions", [{}])[0].get("competitors", [])

            home_team = None
            away_team = None

            home_team_id = None
            away_team_id = None

            for team in competitors:
                team_info = team.get("team", {})
                name = team_info.get("displayName", "")
                tid = team_info.get("id")
                if team.get("homeAway") == "home":
                    home_team = name
                    home_team_id = tid
                else:
                    away_team = name
                    away_team_id = tid

            game_date = event.get("date", "")

            if event_id and home_team and away_team:
                games.append({
                    "event_id": event_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                    "game_date": game_date,
                })

        return games

    except (requests.RequestException, KeyError, IndexError):
        return []


def get_game_spread(event_id):
    """
    Fetches opening and current home team spreads for a given game.

    Args:
        event_id: ESPN event ID

    Returns:
        (opening_spread, current_spread) as floats, or (None, None) on failure
    """
    try:
        response = requests.get(
            ESPN_SUMMARY_URL,
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


def find_game_by_team(team_name):
    """
    Searches today's games for a team name match (case-insensitive substring).

    Args:
        team_name: Team name to search for (e.g., "Lakers", "Los Angeles Lakers")

    Returns:
        event_id if found, None otherwise
    """
    games = get_todays_games()
    search = team_name.strip().lower()

    for game in games:
        if (search in game["home_team"].lower()
                or search in game["away_team"].lower()):
            return game["event_id"]

    return None


def get_all_injuries():
    """
    Fetches current NBA injuries from ESPN.

    Returns:
        Dict mapping team display name → list of injury dicts.
        Each injury dict: {player_name, player_id, status, injury_date, short_comment}
    """
    try:
        response = requests.get(ESPN_INJURIES_URL, timeout=10)
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


def get_player_season_averages(athlete_id):
    """
    Fetches a player's season averages from ESPN.

    Args:
        athlete_id: ESPN athlete ID

    Returns:
        Dict with {ppg, rpg, apg, mpg} or None on failure.
    """
    try:
        url = ESPN_PLAYER_STATS_URL.format(athlete_id)
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        categories = data.get("categories", [])

        stats = {}
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

        if stats.get("ppg") is not None:
            return stats

        return None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None
