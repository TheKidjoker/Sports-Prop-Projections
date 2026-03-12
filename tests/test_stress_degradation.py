"""
Graceful degradation tests — verify the app handles failures without crashing:
- ESPN returns None
- BallDontLie timeout
- All APIs fail
- Supabase unavailable
"""

import requests
from unittest.mock import patch, MagicMock

import pytest

import api_cache
import api_players
import api_client
import game_scanner
import scan_cache
import cache_manager


# ─── Test 1: ESPN returns None ────────────────────────────────────────────────
@pytest.mark.timeout(15, method="thread")
def test_espn_returns_none():
    """get_todays_games returns [] when _cached_request returns None."""
    with patch("api_cache._cached_request", return_value=None):
        # api_client.get_todays_games calls _cached_request internally
        with patch("api_client._cached_request", return_value=None):
            result = api_client.get_todays_games("nba")

    assert isinstance(result, list)
    assert len(result) == 0


# ─── Test 2: BallDontLie timeout ─────────────────────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_balldontlie_timeout():
    """get_player_id and get_player_game_log return None on Timeout."""
    def _raise_timeout(url, **kwargs):
        raise requests.exceptions.Timeout("Connection timed out")

    with patch("api_players.requests.get", side_effect=_raise_timeout):
        pid = api_players.get_player_id("LeBron James")
        assert pid is None

    with patch("api_players.requests.get", side_effect=_raise_timeout), \
         patch("api_players._cached_request", side_effect=lambda *a, **kw: None):
        # Pre-populate player ID so it doesn't try requests.get for ID
        with api_players._player_id_lock:
            api_players._player_id_cache["Test Player"] = 12345
        log = api_players.get_player_game_log("Test Player", sport="nba")
        assert log is None


# ─── Test 3: All APIs fail ───────────────────────────────────────────────────
@pytest.mark.timeout(30, method="thread")
def test_all_apis_fail():
    """scan_all_games returns a list (possibly empty) when all external calls fail."""
    def _raise_conn_error(url, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused")

    with patch("api_cache.requests.get", side_effect=_raise_conn_error), \
         patch("api_players.requests.get", side_effect=_raise_conn_error), \
         patch("api_client._cached_request", return_value=None):
        result = game_scanner.scan_all_games("nba")

    assert isinstance(result, list)


# ─── Test 4: Supabase unavailable ────────────────────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_supabase_unavailable():
    """get_cached_scan returns None, cache_scan returns False when Supabase down."""
    with patch("cache_manager._get_supabase", return_value=None):
        result = cache_manager.get_cached_scan("nba")
        assert result is None

        success = cache_manager.cache_scan("nba", [{"game": 1}])
        assert success is False

        # scan_cache.get should return (None, None) when both memory and DB empty
        with scan_cache._cache_lock:
            scan_cache._cache.clear()
        results, age = scan_cache.get("nba")
        assert results is None
        assert age is None
