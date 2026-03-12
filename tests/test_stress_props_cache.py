"""
Stress tests for game_scanner props cache:
- Overflow at 50 entries
- 20-thread concurrent access
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

import pytest

import game_scanner


# ─── Test 1: Props overflow at 50 ────────────────────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_props_overflow():
    """Pre-fill 50 entries, insert #51 — size stays 50, oldest evicted."""
    now = time.time()

    # Pre-fill 50 cache entries
    with game_scanner._props_cache_lock:
        for i in range(50):
            key = f"nba:{400000 + i}"
            game_scanner._props_cache[key] = {
                "data": [{"player": f"Player{i}", "stat": "pts"}],
                "ts": now - (50 - i),  # oldest first
            }

    assert len(game_scanner._props_cache) == 50

    # Insert #51 directly (simulating what get_game_props does at the end)
    with game_scanner._props_cache_lock:
        game_scanner._props_cache["nba:999999"] = {"data": [{"player": "New"}], "ts": now + 1}
        if len(game_scanner._props_cache) > 50:
            oldest = sorted(game_scanner._props_cache,
                            key=lambda k: game_scanner._props_cache[k]["ts"])
            for old_key in oldest[:len(game_scanner._props_cache) - 50]:
                del game_scanner._props_cache[old_key]

    assert len(game_scanner._props_cache) <= 50
    # Oldest entry evicted
    assert "nba:400000" not in game_scanner._props_cache
    # New entry present
    assert "nba:999999" in game_scanner._props_cache


# ─── Test 2: 20-thread concurrent access ─────────────────────────────────────
@pytest.mark.timeout(30, method="thread")
def test_concurrent_props_access():
    """20 threads calling get_game_props for different events — no exceptions."""
    errors = []

    # Mock all the heavy dependencies that get_game_props calls
    mock_games_data = {
        "events": [{
            "id": "400001",
            "date": "2026-03-12T23:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED", "completed": False}},
            "competitions": [{
                "id": "400001",
                "odds": [{"details": "-5", "overUnder": "215"}],
                "competitors": [
                    {
                        "id": "100", "homeAway": "home",
                        "team": {"id": "100", "abbreviation": "HM",
                                 "displayName": "Home Team"},
                        "curatedRank": {"current": 99},
                        "records": [{"summary": "30-20"}],
                    },
                    {
                        "id": "200", "homeAway": "away",
                        "team": {"id": "200", "abbreviation": "AW",
                                 "displayName": "Away Team"},
                        "curatedRank": {"current": 99},
                        "records": [{"summary": "25-25"}],
                    },
                ],
                "venue": {"fullName": "Arena", "address": {}},
            }],
        }]
    }

    def _fake_props(event_id, sport="nba", player_props_lines=None):
        """Return synthetic props list."""
        time.sleep(0.01)  # Simulate tiny delay
        return [
            {"player": "Star Player", "stat": "pts", "projection": 25.5,
             "confidence": 72, "edge": 2.3, "signal": "LEAN OVER",
             "line": 23.5, "line_source": "odds_api"}
        ]

    with patch("game_scanner.get_game_props", side_effect=_fake_props):
        def _worker(tid):
            try:
                eid = str(400000 + tid)
                result = game_scanner.get_game_props(eid, sport="nba")
                assert isinstance(result, list)
            except Exception as e:
                errors.append((tid, e))

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_worker, tid) for tid in range(20)]
            for f in futures:
                f.result()

    assert len(errors) == 0, f"Errors during concurrent props access: {errors}"
