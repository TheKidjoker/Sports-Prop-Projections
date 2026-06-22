# ─── NBA Advanced Stats Client ────────────────────────────────────────────────
# Fetches advanced team stats from nba.com/stats (public, no API key required).
# Off/def efficiency, four factors, pace, on/off net rating, clutch stats.

import time
import logging
import requests
from api_cache import _cached_request

logger = logging.getLogger(__name__)

BASE_URL = "https://stats.nba.com/stats"

# Required headers to avoid 403 from nba.com
_NBA_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token": "true",
}

# Team abbreviation -> nba.com team ID
NBA_TEAM_IDS = {
    "ATL": 1610612737, "BOS": 1610612738, "BKN": 1610612751, "CHA": 1610612766,
    "CHI": 1610612741, "CLE": 1610612739, "DAL": 1610612742, "DEN": 1610612743,
    "DET": 1610612765, "GSW": 1610612744, "HOU": 1610612745, "IND": 1610612754,
    "LAC": 1610612746, "LAL": 1610612747, "MEM": 1610612763, "MIA": 1610612748,
    "MIL": 1610612749, "MIN": 1610612750, "NOP": 1610612740, "NYK": 1610612752,
    "OKC": 1610612760, "ORL": 1610612753, "PHI": 1610612755, "PHX": 1610612756,
    "POR": 1610612757, "SAC": 1610612758, "SAS": 1610612759, "TOR": 1610612761,
    "UTA": 1610612762, "WAS": 1610612764,
}


def _nba_stats_request(endpoint, params=None):
    """Make a request to stats.nba.com with proper headers."""
    url = f"{BASE_URL}/{endpoint}"
    try:
        response = requests.get(
            url, params=params, headers=_NBA_HEADERS, timeout=15,
        )
        if response.status_code != 200:
            logger.warning("[nba_stats] HTTP %d for %s", response.status_code, endpoint)
            return None
        return response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("[nba_stats] Request failed: %s", e)
        return None


def get_team_advanced_stats(team_abbr, season=None):
    """
    Get team advanced stats: offensive/defensive rating, pace, four factors.

    Args:
        team_abbr: 3-letter abbreviation (e.g., "BOS")
        season: season string (e.g., "2025-26"). Default: current.

    Returns:
        dict with off_rating, def_rating, net_rating, pace, etc.
    """
    if season is None:
        from datetime import date
        today = date.today()
        year = today.year if today.month >= 10 else today.year - 1
        season = f"{year}-{str(year + 1)[-2:]}"

    team_id = NBA_TEAM_IDS.get(team_abbr)

    params = {
        "Conference": "",
        "DateFrom": "",
        "DateTo": "",
        "Division": "",
        "GameScope": "",
        "GameSegment": "",
        "LastNGames": 0,
        "LeagueID": "00",
        "Location": "",
        "MeasureType": "Advanced",
        "Month": 0,
        "OpponentTeamID": 0,
        "Outcome": "",
        "PORound": 0,
        "PaceAdjust": "N",
        "PerMode": "PerGame",
        "Period": 0,
        "PlayerExperience": "",
        "PlayerPosition": "",
        "PlusMinus": "N",
        "Rank": "N",
        "Season": season,
        "SeasonSegment": "",
        "SeasonType": "Regular Season",
        "ShotClockRange": "",
        "StarterBench": "",
        "TeamID": team_id or 0,
        "TwoWay": 0,
        "VsConference": "",
        "VsDivision": "",
    }

    data = _nba_stats_request("leaguedashteamstats", params)
    if not data:
        return None

    result_sets = data.get("resultSets", [])
    if not result_sets:
        return None

    headers = result_sets[0].get("headers", [])
    rows = result_sets[0].get("rowSet", [])

    # Find the team's row
    team_row = None
    for row in rows:
        if team_id and row[0] == team_id:
            team_row = row
            break
        if team_abbr and len(row) > 1 and row[1] == team_abbr:
            team_row = row
            break

    if not team_row:
        return None

    # Map headers to values
    stats = dict(zip(headers, team_row))

    return {
        "team": stats.get("TEAM_NAME"),
        "off_rating": stats.get("OFF_RATING"),
        "def_rating": stats.get("DEF_RATING"),
        "net_rating": stats.get("NET_RATING"),
        "pace": stats.get("PACE"),
        "ts_pct": stats.get("TS_PCT"),
        "efg_pct": stats.get("EFG_PCT"),
        "tov_pct": stats.get("TOV_PCT"),
        "oreb_pct": stats.get("OREB_PCT"),
        "dreb_pct": stats.get("DREB_PCT"),
        "ast_ratio": stats.get("AST_RATIO"),
    }


def get_all_team_advanced_stats(season=None):
    """
    Get advanced stats for all 30 NBA teams in a single request.

    Returns:
        dict of {team_abbr: stats_dict}
    """
    if season is None:
        from datetime import date
        today = date.today()
        year = today.year if today.month >= 10 else today.year - 1
        season = f"{year}-{str(year + 1)[-2:]}"

    params = {
        "Conference": "", "DateFrom": "", "DateTo": "", "Division": "",
        "GameScope": "", "GameSegment": "", "LastNGames": 0,
        "LeagueID": "00", "Location": "", "MeasureType": "Advanced",
        "Month": 0, "OpponentTeamID": 0, "Outcome": "", "PORound": 0,
        "PaceAdjust": "N", "PerMode": "PerGame", "Period": 0,
        "PlayerExperience": "", "PlayerPosition": "", "PlusMinus": "N",
        "Rank": "N", "Season": season, "SeasonSegment": "",
        "SeasonType": "Regular Season", "ShotClockRange": "",
        "StarterBench": "", "TeamID": 0, "TwoWay": 0,
        "VsConference": "", "VsDivision": "",
    }

    data = _nba_stats_request("leaguedashteamstats", params)
    if not data:
        return {}

    result_sets = data.get("resultSets", [])
    if not result_sets:
        return {}

    headers = result_sets[0].get("headers", [])
    rows = result_sets[0].get("rowSet", [])

    all_stats = {}
    for row in rows:
        stats = dict(zip(headers, row))
        abbr = stats.get("TEAM_ABBREVIATION")
        if abbr:
            all_stats[abbr] = {
                "team": stats.get("TEAM_NAME"),
                "off_rating": stats.get("OFF_RATING"),
                "def_rating": stats.get("DEF_RATING"),
                "net_rating": stats.get("NET_RATING"),
                "pace": stats.get("PACE"),
            }

    return all_stats
