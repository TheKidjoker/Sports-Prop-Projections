"""
Timeout enforcement tests:
- get_top_props 45s hard cap (verified by reducing the cap for test)
- Fast return when props are cached
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

import pytest

import game_scanner


# ─── Test 1: get_top_props timeout cap ───────────────────────────────────────
@pytest.mark.timeout(30, method="thread")
def test_get_top_props_timeout_cap():
    """Temporarily reduce max_total_time to 3s, verify function respects it."""
    fake_games = [
        {
            "event_id": str(400000 + i),
            "home_team": f"Home{i}",
            "away_team": f"Away{i}",
            "game_date": "2026-03-12T23:00Z",
            "game_status": "STATUS_SCHEDULED",
        }
        for i in range(3)
    ]

    # Use an event so the slow threads can be interrupted after the test
    stop_event = threading.Event()

    def _slow_props(event_id, sport="nba", player_props_lines=None):
        """Sleep in short intervals, checking the stop event."""
        for _ in range(100):
            if stop_event.is_set():
                return []
            time.sleep(0.1)
        return []

    # Save a reference to the real time.time before patching
    _real_time = time.time
    original_code = game_scanner.get_top_props

    def _patched_top_props(sport="nba"):
        """Wrapper that reduces max_total_time to 3s for test speed."""
        real_start = _real_time()

        def _time_warp():
            elapsed = _real_time() - real_start
            if elapsed > 3:
                # Signal slow threads to exit, then make get_top_props
                # think 46s have passed so it breaks the loop
                stop_event.set()
                return real_start + 46
            return _real_time()

        with patch("game_scanner.time.time", side_effect=_time_warp):
            return original_code(sport)

    with patch("game_scanner.get_todays_games", return_value=fake_games), \
         patch("game_scanner.is_game_stale", return_value=False), \
         patch("game_scanner.get_player_props_odds", return_value={}), \
         patch("game_scanner.get_game_props", side_effect=_slow_props):

        start = time.time()
        result = _patched_top_props("nba")
        elapsed = time.time() - start

    # Should complete quickly: 3s real time before warp + thread cleanup
    assert elapsed < 15, f"get_top_props took {elapsed:.1f}s — should be under 15s"
    assert isinstance(result, list)


# ─── Test 2: Fast return when all games cached ──────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_get_top_props_fast_cached():
    """get_top_props returns quickly when all props are cached."""
    fake_games = [
        {
            "event_id": "400001",
            "home_team": "Home",
            "away_team": "Away",
            "game_date": "2026-03-12T23:00Z",
            "game_status": "STATUS_SCHEDULED",
        }
    ]

    def _fast_props(event_id, sport="nba", player_props_lines=None):
        return [
            {"player": "Star", "stat": "pts", "projection": 25.5,
             "confidence": 72, "edge": 2.3, "signal": "LEAN OVER",
             "line": 23.5, "line_source": "odds_api"}
        ]

    with patch("game_scanner.get_todays_games", return_value=fake_games), \
         patch("game_scanner.is_game_stale", return_value=False), \
         patch("game_scanner.get_player_props_odds", return_value={}), \
         patch("game_scanner.get_game_props", side_effect=_fast_props):

        start = time.time()
        result = game_scanner.get_top_props("nba")
        elapsed = time.time() - start

    assert elapsed < 5, f"Cached props took {elapsed:.1f}s — should be under 5s"
    assert len(result) == 1
    assert result[0]["player"] == "Star"
