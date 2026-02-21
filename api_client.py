import requests

BASE_URL = "https://www.balldontlie.io/api/v1"

# ESPN URL builder
SPORT_MAP = {
    "nba": {"category": "basketball", "league": "nba"},
    "nhl": {"category": "hockey", "league": "nhl"},
    "cfb": {"category": "football", "league": "college-football"},
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


def get_todays_games(sport="nba"):
    """
    Fetches today's games from the ESPN scoreboard API.

    Args:
        sport: "nba" or "nhl"

    Returns:
        List of dicts: [{event_id, home_team, away_team, ...}, ...]
        Empty list on failure.
    """
    try:
        url = _espn_url(sport, "scoreboard")
        response = requests.get(url, timeout=10)
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
                    "venue_name": venue_name,
                    "venue_city": venue_city,
                    "venue_state": venue_state,
                    "home_rank": home_rank,
                    "away_rank": away_rank,
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

        if sport == "nhl":
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
        if sport == "nhl" and stats.get("ptspg") is not None:
            return stats
        elif sport != "nhl" and stats.get("ppg") is not None:
            return stats

        return None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None
