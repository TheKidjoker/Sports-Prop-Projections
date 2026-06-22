# ─── Sport Registry ──────────────────────────────────────────────────────────
# Single source of truth for all sport configuration.
# Consolidates scattered config across constants.py, power_ratings.py,
# api_odds.py, api_cache.py, prism.py, and sport-specific EV models.
#
# Usage:
#   from sport_registry import get_sport, get_all_sports, is_valid_sport
#   sport = get_sport("nba")
#   print(sport["name"], sport["ev_model"], sport["market_type"])

from constants import (
    THRESHOLDS, SOCCER_LEAGUES, POINTS_PER_ELO, STANDARD_OVERROUND,
)
from power_ratings import ELO_CONFIG


# ─── Sport Registry ──────────────────────────────────────────────────────────

SPORT_REGISTRY = {
    "nba": {
        "name": "NBA",
        "full_name": "National Basketball Association",
        "market_type": "spread",
        "ev_model": "nba_ev_model",
        "ev_model_class": "NBAEVModel",
        "scoring_type": "points",
        "league_avg_score": 105.0,
        "default_total": 215.0,
        "elo_config": ELO_CONFIG.get("nba", {}),
        "thresholds": THRESHOLDS.get("nba", {}),
        "points_per_elo": POINTS_PER_ELO.get("nba", 28.0),
        "standard_overround": STANDARD_OVERROUND.get("nba", 0.045),
        "odds_api_key": "basketball_nba",
        "odds_io_key": "basketball-nba",
        "espn_sport": "basketball",
        "espn_league": "nba",
        "has_props": True,
        "has_spreads": True,
        "has_moneyline": True,
        "has_totals": True,
        "seasons": ["regular", "playoffs"],
        "typical_games_per_day": 8,
    },
    "nhl": {
        "name": "NHL",
        "full_name": "National Hockey League",
        "market_type": "puckline",
        "ev_model": "nhl_ev_model",
        "ev_model_class": "NHLEVModel",
        "scoring_type": "goals",
        "league_avg_score": 3.0,
        "default_total": 5.8,
        "elo_config": ELO_CONFIG.get("nhl", {}),
        "thresholds": THRESHOLDS.get("nhl", {}),
        "points_per_elo": POINTS_PER_ELO.get("nhl", 67.0),
        "standard_overround": STANDARD_OVERROUND.get("nhl", 0.050),
        "odds_api_key": "icehockey_nhl",
        "odds_io_key": "ice-hockey-nhl",
        "espn_sport": "hockey",
        "espn_league": "nhl",
        "has_props": True,
        "has_spreads": True,
        "has_moneyline": True,
        "has_totals": True,
        "seasons": ["regular", "playoffs"],
        "typical_games_per_day": 6,
    },
    "nfl": {
        "name": "NFL",
        "full_name": "National Football League",
        "market_type": "spread",
        "ev_model": None,
        "ev_model_class": None,
        "scoring_type": "points",
        "league_avg_score": 22.0,
        "default_total": 44.0,
        "elo_config": ELO_CONFIG.get("nfl", {}),
        "thresholds": THRESHOLDS.get("nfl", {}),
        "points_per_elo": POINTS_PER_ELO.get("nfl", 25.0),
        "standard_overround": STANDARD_OVERROUND.get("nfl", 0.045),
        "odds_api_key": "americanfootball_nfl",
        "odds_io_key": "american-football-nfl",
        "espn_sport": "football",
        "espn_league": "nfl",
        "has_props": False,
        "has_spreads": True,
        "has_moneyline": True,
        "has_totals": True,
        "seasons": ["regular", "playoffs"],
        "typical_games_per_day": 14,
    },
    "cfb": {
        "name": "CFB",
        "full_name": "College Football",
        "market_type": "spread",
        "ev_model": None,
        "ev_model_class": None,
        "scoring_type": "points",
        "league_avg_score": 28.0,
        "default_total": 52.0,
        "elo_config": ELO_CONFIG.get("cfb", {}),
        "thresholds": THRESHOLDS.get("cfb", {}),
        "points_per_elo": POINTS_PER_ELO.get("cfb", 25.0),
        "standard_overround": STANDARD_OVERROUND.get("cfb", 0.045),
        "odds_api_key": "americanfootball_ncaaf",
        "odds_io_key": "american-football-ncaaf",
        "espn_sport": "football",
        "espn_league": "college-football",
        "has_props": False,
        "has_spreads": True,
        "has_moneyline": True,
        "has_totals": True,
        "seasons": ["regular", "bowl"],
        "typical_games_per_day": 40,
    },
    "cbb": {
        "name": "CBB",
        "full_name": "College Basketball",
        "market_type": "spread",
        "ev_model": "cbb_ev_model",
        "ev_model_class": "CBBEVModel",
        "scoring_type": "points",
        "league_avg_score": 75.0,
        "default_total": 150.0,
        "elo_config": ELO_CONFIG.get("cbb", {}),
        "thresholds": THRESHOLDS.get("cbb", {}),
        "points_per_elo": POINTS_PER_ELO.get("cbb", 28.0),
        "standard_overround": STANDARD_OVERROUND.get("cbb", 0.045),
        "odds_api_key": "basketball_ncaab",
        "odds_io_key": "basketball-ncaab",
        "espn_sport": "basketball",
        "espn_league": "mens-college-basketball",
        "has_props": True,
        "has_spreads": True,
        "has_moneyline": True,
        "has_totals": True,
        "seasons": ["regular", "tournament"],
        "typical_games_per_day": 20,
    },
    "mlb": {
        "name": "MLB",
        "full_name": "Major League Baseball",
        "market_type": "moneyline",
        "ev_model": "mlb_ev_model",
        "ev_model_class": "MLBEVModel",
        "scoring_type": "runs",
        "league_avg_score": 4.5,
        "default_total": 8.5,
        "elo_config": ELO_CONFIG.get("mlb", {}),
        "thresholds": THRESHOLDS.get("mlb", {}),
        "points_per_elo": POINTS_PER_ELO.get("mlb", 40.0),
        "standard_overround": STANDARD_OVERROUND.get("mlb", 0.040),
        "odds_api_key": "baseball_mlb",
        "odds_io_key": "baseball-mlb",
        "espn_sport": "baseball",
        "espn_league": "mlb",
        "has_props": True,
        "has_spreads": False,
        "has_moneyline": True,
        "has_totals": True,
        "seasons": ["regular", "playoffs"],
        "typical_games_per_day": 15,
    },
    "soccer": {
        "name": "Soccer",
        "full_name": "Association Football",
        "market_type": "1x2",
        "ev_model": "soccer_ev_model",
        "ev_model_class": "SoccerEVModel",
        "scoring_type": "goals",
        "league_avg_score": 1.35,
        "default_total": 2.7,
        "elo_config": ELO_CONFIG.get("soccer", {}),
        "thresholds": THRESHOLDS.get("soccer", {}),
        "points_per_elo": POINTS_PER_ELO.get("soccer", 35.0),
        "standard_overround": STANDARD_OVERROUND.get("soccer", 0.055),
        "odds_api_key": "soccer_epl",
        "odds_io_key": None,
        "espn_sport": None,
        "espn_league": None,
        "has_props": True,
        "has_spreads": False,
        "has_moneyline": False,
        "has_totals": True,
        "has_1x2": True,
        "has_asian_handicap": True,
        "has_btts": True,
        "leagues": SOCCER_LEAGUES,
        "seasons": ["regular"],
        "typical_games_per_day": 10,
    },
}


# ─── Public API ──────────────────────────────────────────────────────────────

def get_sport(sport_key):
    """Get sport configuration by key. Returns None if not found."""
    return SPORT_REGISTRY.get(sport_key)


def get_all_sports():
    """Get all sport keys."""
    return list(SPORT_REGISTRY.keys())


def is_valid_sport(sport_key):
    """Check if a sport key is valid."""
    return sport_key in SPORT_REGISTRY


def get_us_sports():
    """Get US-based sports (spread/moneyline markets)."""
    return [k for k, v in SPORT_REGISTRY.items() if v["market_type"] != "1x2"]


def get_ev_model_sports():
    """Get sports that have EV models."""
    return [k for k, v in SPORT_REGISTRY.items() if v["ev_model"] is not None]


def get_sport_by_odds_api_key(odds_key):
    """Reverse lookup: find sport by Odds API sport key."""
    for k, v in SPORT_REGISTRY.items():
        if v.get("odds_api_key") == odds_key:
            return k
    return None


def get_sport_display_name(sport_key):
    """Get human-readable sport name."""
    sport = SPORT_REGISTRY.get(sport_key)
    return sport["name"] if sport else sport_key.upper()


# ─── Derived Mapping Helpers ──────────────────────────────────────────────────
# These replace duplicate dicts that were scattered across api_odds.py,
# api_odds_io.py, tracker.py, test_model/collector.py, and api_cache.py.

def get_odds_api_sport_map():
    """
    Returns {sport_key: odds_api_key} for all sports.
    Includes soccer league variants for The Odds API.
    """
    base = {k: v["odds_api_key"] for k, v in SPORT_REGISTRY.items() if v.get("odds_api_key")}
    # Add soccer league variants (The Odds API uses these keys directly)
    base.update({
        "soccer_epl": "soccer_epl",
        "soccer_spain_la_liga": "soccer_spain_la_liga",
        "soccer_germany_bundesliga": "soccer_germany_bundesliga",
        "soccer_italy_serie_a": "soccer_italy_serie_a",
        "soccer_france_ligue_one": "soccer_france_ligue_one",
        "soccer_usa_mls": "soccer_usa_mls",
        "soccer_uefa_champs_league": "soccer_uefa_champs_league",
        "soccer_netherlands_eredivisie": "soccer_netherlands_eredivisie",
        "soccer_portugal_primeira_liga": "soccer_portugal_primeira_liga",
        "soccer_turkey_super_league": "soccer_turkey_super_league",
        "soccer_england_league1": "soccer_england_league1",
        "soccer_mexico_ligamx": "soccer_mexico_ligamx",
        "soccer_australia_aleague": "soccer_australia_aleague",
        "soccer_japan_j_league": "soccer_japan_j_league",
        "soccer_korea_kleague1": "soccer_korea_kleague1",
        "soccer_saudi_pro_league": "soccer_saudi_professional_league",
    })
    return base


def get_odds_io_sport_map():
    """
    Returns {sport_key: {"sport": ..., "league": ...}} for odds-api.io.
    """
    result = {}
    for k, v in SPORT_REGISTRY.items():
        io_key = v.get("odds_io_key")
        if io_key:
            parts = io_key.rsplit("-", 1)
            # Handle multi-word sport names like "ice-hockey" and "american-football"
            if k == "nhl":
                result[k] = {"sport": "ice-hockey", "league": "nhl"}
            elif k in ("nfl", "cfb"):
                league = "nfl" if k == "nfl" else "ncaaf"
                result[k] = {"sport": "american-football", "league": league}
            elif k == "cbb":
                result[k] = {"sport": "basketball", "league": "ncaab"}
            else:
                result[k] = {"sport": parts[0], "league": parts[1] if len(parts) > 1 else k}
    # Soccer league variants for odds-api.io
    result.update({
        "soccer_epl": {"sport": "soccer", "league": "england-premier-league"},
        "soccer_spain_la_liga": {"sport": "soccer", "league": "spain-la-liga"},
        "soccer_germany_bundesliga": {"sport": "soccer", "league": "germany-bundesliga"},
        "soccer_italy_serie_a": {"sport": "soccer", "league": "italy-serie-a"},
        "soccer_france_ligue_one": {"sport": "soccer", "league": "france-ligue-1"},
        "soccer_usa_mls": {"sport": "soccer", "league": "usa-mls"},
        "soccer_uefa_champs_league": {"sport": "soccer", "league": "uefa-champions-league"},
    })
    return result


def get_espn_sport_map():
    """
    Returns {sport_key: {"category": espn_sport, "league": espn_league}}.
    """
    result = {}
    for k, v in SPORT_REGISTRY.items():
        if v.get("espn_sport") and v.get("espn_league"):
            result[k] = {"category": v["espn_sport"], "league": v["espn_league"]}
    # Soccer uses eng.1 for ESPN
    if "soccer" not in result:
        result["soccer"] = {"category": "soccer", "league": "eng.1"}
    return result
