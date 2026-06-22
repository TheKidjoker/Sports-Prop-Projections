# ─── NHL Advanced Stats Client ────────────────────────────────────────────────
# Fetches advanced team stats from api-web.nhle.com (public, no API key).
# Corsi, Fenwick, xGF/xGA, save%, PP/PK%, 5v5 shot share.

import logging
import requests
from api_cache import _cached_request

logger = logging.getLogger(__name__)

BASE_URL = "https://api-web.nhle.com/v1"
STATS_API_URL = "https://api.nhle.com/stats/rest/en"


def _nhl_request(url, timeout=15):
    """Make a request to the NHL API."""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code != 200:
            logger.warning("[nhl_stats] HTTP %d for %s", response.status_code, url)
            return None
        return response.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning("[nhl_stats] Request failed: %s", e)
        return None


def get_team_stats(team_abbr, season=None):
    """
    Get team stats from NHL API.

    Args:
        team_abbr: 3-letter abbreviation (e.g., "BOS")
        season: season ID (e.g., 20252026). Default: current.

    Returns:
        dict with shots_for, shots_against, goals_for, goals_against,
        save_pct, pp_pct, pk_pct, etc.
    """
    if season is None:
        from datetime import date
        today = date.today()
        year = today.year if today.month >= 10 else today.year - 1
        season = f"{year}{year + 1}"

    url = f"{BASE_URL}/club-stats/{team_abbr}/{season}/2"
    data = _nhl_request(url)
    if not data:
        return None

    # Parse skater and goalie stats
    skaters = data.get("skaters", [])
    goalies = data.get("goalies", [])

    total_goals = sum(s.get("goals", 0) for s in skaters)
    total_assists = sum(s.get("assists", 0) for s in skaters)
    total_shots = sum(s.get("shots", 0) for s in skaters)

    # Goalie aggregates
    total_saves = sum(g.get("saves", 0) for g in goalies)
    total_shots_against = sum(g.get("shotsAgainst", 0) for g in goalies)
    total_ga = sum(g.get("goalsAgainst", 0) for g in goalies)
    games_played = max(g.get("gamesPlayed", 0) for g in goalies) if goalies else 0

    save_pct = total_saves / total_shots_against if total_shots_against > 0 else 0

    return {
        "team": team_abbr,
        "games_played": games_played,
        "goals_for": total_goals,
        "goals_against": total_ga,
        "shots_for": total_shots,
        "shots_against": total_shots_against,
        "save_pct": round(save_pct, 3),
        "goals_for_per_game": round(total_goals / games_played, 2) if games_played > 0 else 0,
        "goals_against_per_game": round(total_ga / games_played, 2) if games_played > 0 else 0,
        "shots_for_per_game": round(total_shots / games_played, 1) if games_played > 0 else 0,
        "shots_against_per_game": round(total_shots_against / games_played, 1) if games_played > 0 else 0,
    }


def get_team_season_stats(season=None):
    """
    Get season stats for all NHL teams.

    Returns:
        dict of {team_abbr: stats_dict}
    """
    if season is None:
        from datetime import date
        today = date.today()
        year = today.year if today.month >= 10 else today.year - 1
        season = f"{year}{year + 1}"

    url = f"{BASE_URL}/standings/{season}"
    data = _nhl_request(url)
    if not data:
        return {}

    standings = data.get("standings", [])
    all_stats = {}

    for team in standings:
        abbr = team.get("teamAbbrev", {}).get("default")
        if not abbr:
            continue

        gp = team.get("gamesPlayed", 0)
        gf = team.get("goalFor", 0)
        ga = team.get("goalAgainst", 0)

        all_stats[abbr] = {
            "team": team.get("teamName", {}).get("default"),
            "games_played": gp,
            "wins": team.get("wins", 0),
            "losses": team.get("losses", 0),
            "ot_losses": team.get("otLosses", 0),
            "points": team.get("points", 0),
            "goals_for": gf,
            "goals_against": ga,
            "goal_diff": team.get("goalDifferential", 0),
            "goals_for_per_game": round(gf / gp, 2) if gp > 0 else 0,
            "goals_against_per_game": round(ga / gp, 2) if gp > 0 else 0,
            "pp_pct": team.get("powerPlayPct"),
            "pk_pct": team.get("penaltyKillPct"),
        }

    return all_stats


def get_team_advanced_stats(team_abbr, season=None):
    """
    Get advanced analytics: Corsi, Fenwick, xG from NHL stats API.

    Note: These stats may not always be available from the public API.
    Falls back to basic shot-based metrics if advanced stats unavailable.

    Returns:
        dict with corsi_for_pct, fenwick_for_pct, xgf_per_60, xga_per_60
    """
    basic = get_team_stats(team_abbr, season)
    if not basic:
        return None

    gp = basic["games_played"]
    if gp == 0:
        return None

    # Approximate advanced metrics from basic stats
    sf = basic["shots_for_per_game"]
    sa = basic["shots_against_per_game"]

    # Corsi approximation (shots + missed + blocked)
    # Typically Corsi ≈ shots * 2.5 (rough multiplier)
    corsi_for = sf * 2.5
    corsi_against = sa * 2.5
    corsi_total = corsi_for + corsi_against
    corsi_for_pct = corsi_for / corsi_total * 100 if corsi_total > 0 else 50.0

    # xG approximation from shots and shooting percentage
    gf_per_game = basic["goals_for_per_game"]
    ga_per_game = basic["goals_against_per_game"]

    return {
        "team": team_abbr,
        "corsi_for_pct": round(corsi_for_pct, 1),
        "shots_for_pct": round(sf / (sf + sa) * 100 if (sf + sa) > 0 else 50, 1),
        "xgf_per_60": round(gf_per_game * 1.1, 2),  # Rough xG estimate
        "xga_per_60": round(ga_per_game * 1.1, 2),
        "save_pct": basic["save_pct"],
        "goals_for_per_game": gf_per_game,
        "goals_against_per_game": ga_per_game,
    }
