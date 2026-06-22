# ─── Soccer API Client (API-Football) ─────────────────────────────────────────
# Fetches fixtures, xG, team stats, H2H, lineups from api-football.com.
# Supports 1000+ leagues via API-Football (RapidAPI).

import os
import time
import logging
import requests
from api_cache import _cached_request

logger = logging.getLogger(__name__)

BASE_URL = "https://v3.football.api-sports.io"
RAPID_API_URL = "https://api-football-v1.p.rapidapi.com/v3"

# Rate limit: 10 req/min on free tier, 300/min on paid
_rate_limit = {"remaining": None, "last_request": 0}
_MIN_INTERVAL = 0.2  # 200ms between requests


def _get_api_key():
    return os.environ.get("FOOTBALL_API_KEY", "")


def _get_headers():
    key = _get_api_key()
    if not key:
        return None
    # Support both direct API and RapidAPI
    if key.startswith("rapid_"):
        return {
            "x-rapidapi-host": "api-football-v1.p.rapidapi.com",
            "x-rapidapi-key": key.replace("rapid_", ""),
        }
    return {"x-apisports-key": key}


def _api_request(endpoint, params=None):
    """Make a rate-limited request to API-Football."""
    headers = _get_headers()
    if not headers:
        logger.debug("[soccer_api] No FOOTBALL_API_KEY set")
        return None

    # Rate limiting
    now = time.time()
    elapsed = now - _rate_limit["last_request"]
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        _rate_limit["last_request"] = time.time()

        if response.status_code == 429:
            logger.warning("[soccer_api] Rate limited, waiting 60s")
            time.sleep(60)
            return None

        if response.status_code != 200:
            logger.warning("[soccer_api] HTTP %d for %s", response.status_code, endpoint)
            return None

        data = response.json()
        if data.get("errors"):
            logger.warning("[soccer_api] API errors: %s", data["errors"])
            return None

        return data.get("response", [])
    except (requests.RequestException, ValueError) as e:
        logger.warning("[soccer_api] Request failed: %s", e)
        return None


def is_available():
    """Check if the API key is configured."""
    return bool(_get_api_key())


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def get_fixtures(league_id, date_str=None, season=None):
    """
    Get fixtures for a league on a specific date.

    Args:
        league_id: API-Football league ID (e.g., 39 for EPL)
        date_str: date string YYYY-MM-DD (default: today)
        season: season year (e.g., 2025)

    Returns:
        list of fixture dicts
    """
    if date_str is None:
        from datetime import date
        date_str = date.today().isoformat()

    if season is None:
        season = int(date_str[:4])
        # Adjust for European seasons that span two calendar years
        month = int(date_str[5:7])
        if month < 7:
            season -= 1

    params = {
        "league": league_id,
        "date": date_str,
        "season": season,
    }
    raw = _api_request("fixtures", params)
    if not raw:
        return []

    fixtures = []
    for f in raw:
        fixture = f.get("fixture", {})
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        score = f.get("score", {})

        fixtures.append({
            "fixture_id": fixture.get("id"),
            "date": fixture.get("date"),
            "status": fixture.get("status", {}).get("short"),
            "venue": fixture.get("venue", {}).get("name"),
            "home_team": teams.get("home", {}).get("name"),
            "away_team": teams.get("away", {}).get("name"),
            "home_team_id": teams.get("home", {}).get("id"),
            "away_team_id": teams.get("away", {}).get("id"),
            "home_goals": goals.get("home"),
            "away_goals": goals.get("away"),
            "halftime": score.get("halftime", {}),
        })

    return fixtures


# ─── Team Statistics ──────────────────────────────────────────────────────────

def get_team_stats(team_id, league_id, season=None):
    """
    Get comprehensive team statistics for a season.

    Returns:
        dict with form, goals, xG, clean sheets, etc.
    """
    if season is None:
        from datetime import date
        season = date.today().year
        if date.today().month < 7:
            season -= 1

    params = {"team": team_id, "league": league_id, "season": season}
    raw = _api_request("teams/statistics", params)
    if not raw:
        return None

    # API returns a single object, not a list
    stats = raw if isinstance(raw, dict) else raw[0] if raw else None
    if not stats:
        return None

    goals_for = stats.get("goals", {}).get("for", {})
    goals_against = stats.get("goals", {}).get("against", {})

    return {
        "form": stats.get("form", ""),
        "games_played": stats.get("fixtures", {}).get("played", {}).get("total", 0),
        "wins": stats.get("fixtures", {}).get("wins", {}).get("total", 0),
        "draws": stats.get("fixtures", {}).get("draws", {}).get("total", 0),
        "losses": stats.get("fixtures", {}).get("losses", {}).get("total", 0),
        "goals_for_total": goals_for.get("total", {}).get("total", 0),
        "goals_for_avg": goals_for.get("average", {}).get("total"),
        "goals_against_total": goals_against.get("total", {}).get("total", 0),
        "goals_against_avg": goals_against.get("average", {}).get("total"),
        "clean_sheets": stats.get("clean_sheet", {}).get("total", 0),
        "failed_to_score": stats.get("failed_to_score", {}).get("total", 0),
    }


# ─── Head-to-Head ────────────────────────────────────────────────────────────

def get_h2h(team1_id, team2_id, last_n=5):
    """
    Get head-to-head results between two teams.

    Returns:
        list of recent H2H fixture dicts
    """
    params = {"h2h": f"{team1_id}-{team2_id}", "last": last_n}
    raw = _api_request("fixtures/headtohead", params)
    if not raw:
        return []

    results = []
    for f in raw:
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        results.append({
            "date": f.get("fixture", {}).get("date"),
            "home_team": teams.get("home", {}).get("name"),
            "away_team": teams.get("away", {}).get("name"),
            "home_goals": goals.get("home"),
            "away_goals": goals.get("away"),
        })

    return results


# ─── Expected Goals (xG) ─────────────────────────────────────────────────────

def get_fixture_xg(fixture_id):
    """
    Get xG data for a specific fixture (post-match or live).

    Returns:
        dict with home_xg, away_xg or None
    """
    params = {"id": fixture_id}
    raw = _api_request("fixtures", params)
    if not raw:
        return None

    fixture = raw[0] if raw else None
    if not fixture:
        return None

    stats = fixture.get("statistics", [])
    home_xg = None
    away_xg = None

    for team_stats in stats:
        team_name = team_stats.get("team", {}).get("name")
        for stat in team_stats.get("statistics", []):
            if stat.get("type") == "expected_goals":
                val = stat.get("value")
                if val is not None:
                    try:
                        xg = float(val)
                    except (ValueError, TypeError):
                        continue
                    # First team = home, second = away
                    if home_xg is None:
                        home_xg = xg
                    else:
                        away_xg = xg

    if home_xg is not None and away_xg is not None:
        return {"home_xg": home_xg, "away_xg": away_xg}
    return None


# ─── Standings ────────────────────────────────────────────────────────────────

def get_standings(league_id, season=None):
    """Get league standings."""
    if season is None:
        from datetime import date
        season = date.today().year
        if date.today().month < 7:
            season -= 1

    params = {"league": league_id, "season": season}
    raw = _api_request("standings", params)
    if not raw:
        return []

    standings = []
    for league in raw:
        for group in league.get("league", {}).get("standings", []):
            for team in group:
                standings.append({
                    "rank": team.get("rank"),
                    "team": team.get("team", {}).get("name"),
                    "team_id": team.get("team", {}).get("id"),
                    "points": team.get("points"),
                    "played": team.get("all", {}).get("played"),
                    "win": team.get("all", {}).get("win"),
                    "draw": team.get("all", {}).get("draw"),
                    "lose": team.get("all", {}).get("lose"),
                    "goals_for": team.get("all", {}).get("goals", {}).get("for"),
                    "goals_against": team.get("all", {}).get("goals", {}).get("against"),
                    "goal_diff": team.get("goalsDiff"),
                    "form": team.get("form"),
                })

    return standings


# ─── Player Stats ─────────────────────────────────────────────────────────────

def get_top_scorers(league_id, season=None):
    """Get top scorers for a league season."""
    if season is None:
        from datetime import date
        season = date.today().year
        if date.today().month < 7:
            season -= 1

    params = {"league": league_id, "season": season}
    raw = _api_request("players/topscorers", params)
    if not raw:
        return []

    scorers = []
    for p in raw[:20]:
        player = p.get("player", {})
        stats = p.get("statistics", [{}])[0] if p.get("statistics") else {}
        goals_data = stats.get("goals", {})
        scorers.append({
            "name": player.get("name"),
            "player_id": player.get("id"),
            "team": stats.get("team", {}).get("name"),
            "goals": goals_data.get("total", 0),
            "assists": goals_data.get("assists", 0),
            "games": stats.get("games", {}).get("appearences", 0),
        })

    return scorers
