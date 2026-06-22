"""
Shared fixtures for stress tests.

Patches all DB init functions and scan_cache.init to no-op BEFORE importing app,
resets all in-memory caches between tests, and provides mock factories.
"""

import os
import sys
import threading
import time

import pytest

# ─── Environment setup (must happen before any app imports) ───────────────────
os.environ["SUPABASE_JWT_SECRET"] = ""  # Auth bypass for tests
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_ANON_KEY"] = ""
os.environ.setdefault("SCAN_GAME_WORKERS", "2")
os.environ.setdefault("SCAN_API_WORKERS", "2")

# Ensure the project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# ─── Patch startup side-effects before importing anything ─────────────────────
import unittest.mock as _mock

# Prevent background threads and DB init during import
_patches = [
    _mock.patch("scan_cache.init", lambda: None),
    _mock.patch("tracker.init_db", lambda: None),
    _mock.patch("bet_tracker.init_tracked_bets_db", lambda: None),
    _mock.patch("pick_curation.init_pick_approvals_db", lambda: None),
    _mock.patch("cache_manager._get_supabase", lambda: None),
]

for _p in _patches:
    _p.start()

# Now safe to import app modules
import api_cache
import api_players
import game_scanner
import scan_cache


# ─── Cache reset fixture (autouse) ───────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_all_caches():
    """Clear every in-memory cache before each test."""
    # api_cache
    with api_cache._cache_lock:
        api_cache._cache.clear()

    # api_players — player ID cache
    with api_players._player_id_lock:
        api_players._player_id_cache.clear()

    # api_players — game log cache
    with api_players._game_log_lock:
        api_players._game_log_cache.clear()

    # game_scanner — props cache
    with game_scanner._props_cache_lock:
        game_scanner._props_cache.clear()

    # scan_cache — in-memory cache
    with scan_cache._cache_lock:
        scan_cache._cache.clear()

    yield

    # Post-test cleanup (same thing)
    with api_cache._cache_lock:
        api_cache._cache.clear()
    with api_players._player_id_lock:
        api_players._player_id_cache.clear()
    with api_players._game_log_lock:
        api_players._game_log_cache.clear()
    with game_scanner._props_cache_lock:
        game_scanner._props_cache.clear()
    with scan_cache._cache_lock:
        scan_cache._cache.clear()


# ─── Lock-file cleanup ───────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _cleanup_lock_file():
    """Remove scan_cache lock file if tests create one."""
    yield
    lock_file = scan_cache._LOCK_FILE
    if os.path.exists(lock_file):
        try:
            os.unlink(lock_file)
        except OSError:
            pass


# ─── Synthetic data factories ────────────────────────────────────────────────
def make_espn_scoreboard(num_games=8):
    """Return a synthetic ESPN scoreboard JSON with N games."""
    events = []
    for i in range(num_games):
        events.append({
            "id": str(400000 + i),
            "date": "2026-03-12T23:00Z",
            "status": {
                "type": {"name": "STATUS_SCHEDULED", "completed": False}
            },
            "competitions": [{
                "id": str(400000 + i),
                "odds": [{"details": f"-{3 + i}", "overUnder": f"{210 + i}"}],
                "competitors": [
                    {
                        "id": str(100 + i),
                        "homeAway": "home",
                        "team": {
                            "id": str(100 + i),
                            "abbreviation": f"HM{i}",
                            "displayName": f"Home Team {i}",
                        },
                        "curatedRank": {"current": 99},
                        "records": [{"summary": "30-20"}],
                    },
                    {
                        "id": str(200 + i),
                        "homeAway": "away",
                        "team": {
                            "id": str(200 + i),
                            "abbreviation": f"AW{i}",
                            "displayName": f"Away Team {i}",
                        },
                        "curatedRank": {"current": 99},
                        "records": [{"summary": "25-25"}],
                    },
                ],
                "venue": {"fullName": "Test Arena", "address": {}},
            }],
        })
    return {"events": events}


def make_player_search(player_name, player_id=12345):
    """Return synthetic BallDontLie player search response."""
    return {
        "data": [{
            "id": player_id,
            "first_name": player_name.split()[0] if " " in player_name else player_name,
            "last_name": player_name.split()[-1] if " " in player_name else "",
        }]
    }


def make_game_log(num_games=5):
    """Return synthetic BallDontLie stats response."""
    return {
        "data": [
            {
                "pts": 20 + i,
                "reb": 5 + i,
                "ast": 3 + i,
                "min": f"32:{i:02d}",
                "game": {"date": f"2026-03-{10 - i:02d}T00:00:00Z"},
            }
            for i in range(num_games)
        ]
    }


# ─── Unit Test Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def sample_game_dict():
    """A fully-populated game analysis dict for unit tests."""
    return {
        "event_id": "401234567",
        "home_team": "Boston Celtics",
        "away_team": "New York Knicks",
        "home_team_id": "2",
        "away_team_id": "18",
        "current_spread": -6.5,
        "opening_spread": -5.5,
        "slot_type": "vegas",
        "lean_team": "New York Knicks",
        "confirmation_score": 12,
        "cover_pct": 68.5,
        "recommendation": "LEAN",
        "sport": "nba",
    }


@pytest.fixture
def sample_odds_data():
    """Mock odds API response for testing."""
    return [
        {
            "home_team": "Boston Celtics",
            "away_team": "New York Knicks",
            "bookmakers": [
                {
                    "key": "pinnacle",
                    "title": "Pinnacle",
                    "markets": [
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Boston Celtics", "price": -110, "point": -6.5},
                                {"name": "New York Knicks", "price": -110, "point": 6.5},
                            ],
                        },
                        {
                            "key": "h2h",
                            "outcomes": [
                                {"name": "Boston Celtics", "price": -250},
                                {"name": "New York Knicks", "price": 200},
                            ],
                        },
                    ],
                },
                {
                    "key": "fanduel",
                    "title": "FanDuel",
                    "markets": [
                        {
                            "key": "spreads",
                            "outcomes": [
                                {"name": "Boston Celtics", "price": -110, "point": -7.0},
                                {"name": "New York Knicks", "price": -110, "point": 7.0},
                            ],
                        },
                    ],
                },
            ],
        }
    ]


@pytest.fixture
def mock_elo_cache():
    """Provide a mock Elo ratings dict for testing without DB."""
    return {
        "nba": {
            "Boston Celtics": 1620,
            "New York Knicks": 1530,
            "Los Angeles Lakers": 1480,
            "Golden State Warriors": 1550,
        },
        "nhl": {
            "Boston Bruins": 1580,
            "Toronto Maple Leafs": 1540,
            "New York Rangers": 1520,
        },
        "soccer": {
            "Manchester City": 1650,
            "Arsenal": 1600,
            "Liverpool": 1590,
            "Manchester United": 1480,
        },
    }


@pytest.fixture
def sample_recent_games():
    """Player game logs for prop variance/projection testing."""
    return [
        {"pts": 28, "reb": 8, "ast": 5, "min": 35, "g": 0, "sog": 3},
        {"pts": 22, "reb": 6, "ast": 7, "min": 33, "g": 1, "sog": 4},
        {"pts": 31, "reb": 9, "ast": 4, "min": 36, "g": 0, "sog": 2},
        {"pts": 25, "reb": 7, "ast": 6, "min": 34, "g": 1, "sog": 5},
        {"pts": 19, "reb": 5, "ast": 3, "min": 30, "g": 0, "sog": 3},
        {"pts": 27, "reb": 8, "ast": 5, "min": 34, "g": 0, "sog": 4},
        {"pts": 24, "reb": 6, "ast": 4, "min": 32, "g": 1, "sog": 3},
        {"pts": 30, "reb": 10, "ast": 6, "min": 37, "g": 0, "sog": 2},
        {"pts": 21, "reb": 7, "ast": 5, "min": 31, "g": 0, "sog": 3},
        {"pts": 26, "reb": 8, "ast": 4, "min": 33, "g": 0, "sog": 4},
    ]


@pytest.fixture
def sample_soccer_match():
    """A soccer match fixture for soccer engine testing."""
    return {
        "fixture_id": 867530,
        "league": "epl",
        "home_team": "Manchester City",
        "away_team": "Arsenal",
        "home_xg": 1.8,
        "away_xg": 1.3,
        "home_xga": 0.9,
        "away_xga": 1.1,
        "home_form_5": "WWDWW",
        "away_form_5": "WLWWW",
        "h2h_goals_diff": 0.5,
        "home_advantage_league": 0.46,
        "match_importance": 0.8,
    }
