"""
Stress tests for api_players caches:
- Player ID FIFO eviction at _PLAYER_ID_MAX (500)
- Game log TTL boundary (1800s)
- Game log overflow at _GAME_LOG_MAX (200)
"""

import time
from unittest.mock import patch, MagicMock

import pytest

import api_players


class _FakeResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


# ─── Test 1: Player ID FIFO at 500 ───────────────────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_player_id_fifo_eviction():
    """Fill 500 players, add #501 — first ~100 (20%) evicted, 101-501 remain."""
    # Pre-fill 500 entries directly
    with api_players._player_id_lock:
        for i in range(500):
            api_players._player_id_cache[f"Player {i}"] = 10000 + i

    assert len(api_players._player_id_cache) == 500

    # Add player #501 via actual function (triggers eviction)
    def _fake_get(url, **kwargs):
        return _FakeResponse({"data": [{"id": 99999}]})

    with patch("api_players.requests.get", side_effect=_fake_get):
        result = api_players.get_player_id("Player New")

    assert result == 99999

    # FIFO: oldest 20% (first 100) evicted
    cache = api_players._player_id_cache
    assert len(cache) <= 401  # 500 - 100 + 1

    # First entries should be gone
    assert "Player 0" not in cache
    assert "Player 50" not in cache

    # Later entries should survive
    assert "Player 200" in cache
    assert "Player 499" in cache
    assert "Player New" in cache


# ─── Test 2: Game log TTL boundary ───────────────────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_game_log_ttl_boundary():
    """Insert at T, check at T+1799 (hit) and T+1801 (miss)."""
    fake_log = [{"pts": 25, "reb": 5, "ast": 3, "min": 32, "date": "2026-03-10"}]
    base_time = 1000000.0
    current_time = {"t": base_time}

    # Pre-populate the player ID cache so get_player_id doesn't make HTTP calls
    with api_players._player_id_lock:
        api_players._player_id_cache["Test Player"] = 12345

    call_count = {"n": 0}

    def _fake_cached_request(url, **kwargs):
        call_count["n"] += 1
        return {
            "data": [{
                "pts": 25, "reb": 5, "ast": 3, "min": "32:00",
                "game": {"date": "2026-03-10T00:00:00Z"}
            }]
        }

    # Seed cache entry at base_time
    with api_players._game_log_lock:
        api_players._game_log_cache["Test Player|7"] = {
            "data": fake_log,
            "ts": base_time,
        }

    with patch("api_players._time.time") as mock_time, \
         patch("api_players._cached_request", side_effect=_fake_cached_request):

        # At T+1799: should be a cache HIT (within 1800s TTL)
        mock_time.return_value = base_time + 1799
        result1 = api_players.get_player_game_log("Test Player", count=7, sport="nba")
        assert result1 == fake_log
        assert call_count["n"] == 0, "Should not have fetched — TTL not expired"

        # At T+1801: should be a cache MISS (TTL expired)
        mock_time.return_value = base_time + 1801
        result2 = api_players.get_player_game_log("Test Player", count=7, sport="nba")
        assert result2 is not None
        assert call_count["n"] == 1, "Should have fetched exactly once — TTL expired"


# ─── Test 3: Game log overflow at 200 ────────────────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_game_log_overflow():
    """Fill 200 entries, insert #201 — size stays 200, oldest evicted."""
    now = time.time()

    # Pre-fill 200 entries
    with api_players._game_log_lock:
        for i in range(200):
            key = f"Player{i}|7"
            api_players._game_log_cache[key] = {
                "data": [{"pts": i}],
                "ts": now - (200 - i),  # oldest first
            }

    assert len(api_players._game_log_cache) == 200

    # Pre-populate player ID cache
    with api_players._player_id_lock:
        api_players._player_id_cache["NewPlayer"] = 99999

    def _fake_cached_request(url, **kwargs):
        return {
            "data": [{
                "pts": 999, "reb": 0, "ast": 0, "min": "30:00",
                "game": {"date": "2026-03-12T00:00:00Z"}
            }]
        }

    with patch("api_players._time.time", return_value=now + 10), \
         patch("api_players._cached_request", side_effect=_fake_cached_request):
        result = api_players.get_player_game_log("NewPlayer", count=7, sport="nba")

    assert result is not None
    assert len(api_players._game_log_cache) <= 200

    # Oldest entry should be evicted
    assert "Player0|7" not in api_players._game_log_cache
    # Newest should exist
    assert "NewPlayer|7" in api_players._game_log_cache
