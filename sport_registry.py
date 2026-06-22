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
