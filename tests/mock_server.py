"""
Mock server for Locust load testing.

Starts the Flask app with all external APIs patched so no real HTTP calls are made.
Run this, then point Locust at it.

Usage:
    python tests/mock_server.py
    :: Then in another terminal:
    python -m locust -f locustfile.py -H http://localhost:5055
    :: Open http://localhost:8089 in browser
"""

import os
import sys
import json
import time

# Ensure project root on path
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

# ─── Environment: disable auth, Supabase, external APIs ──────────────────────
os.environ["SUPABASE_JWT_SECRET"] = ""
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_ANON_KEY"] = ""
os.environ["SCAN_GAME_WORKERS"] = "2"
os.environ["SCAN_API_WORKERS"] = "2"

# ─── Patch BEFORE importing anything from the app ────────────────────────────
import unittest.mock as mock

# These modules are imported by app.py at module level, so we import them
# first and patch their init functions before app.py calls them.
import scan_cache
import tracker
import bet_tracker
import pick_curation
import cache_manager

# Prevent background threads and DB init
scan_cache.init = lambda: None
tracker.init_db = lambda: None
bet_tracker.init_tracked_bets_db = lambda: None
pick_curation.init_pick_approvals_db = lambda: None
cache_manager._get_supabase = lambda: None

# Prevent the auto-tm thread from starting by patching threading.Thread.start
# for the specific auto-tm thread
_real_thread_start = __import__("threading").Thread.start


def _guarded_thread_start(self):
    """Block the auto-tm background thread, allow all others."""
    if getattr(self, "name", "") == "scan-cache":
        return  # Already handled by scan_cache.init = noop
    if hasattr(self, "_target") and self._target and "auto_run_test_model" in str(self._target):
        print("[mock_server] Blocked auto-tm background thread", flush=True)
        return
    _real_thread_start(self)


# Synthetic ESPN scoreboard (8 games)
_SCOREBOARD = {
    "events": [
        {
            "id": str(400000 + i),
            "date": "2026-03-12T23:00Z",
            "status": {"type": {"name": "STATUS_SCHEDULED", "completed": False}},
            "competitions": [{
                "id": str(400000 + i),
                "odds": [{"details": f"-{3 + i}", "overUnder": f"{210 + i}"}],
                "competitors": [
                    {
                        "id": str(100 + i), "homeAway": "home",
                        "team": {"id": str(100 + i), "abbreviation": f"HM{i}",
                                 "displayName": f"Home Team {i}"},
                        "curatedRank": {"current": 99},
                        "records": [{"summary": "30-20"}],
                    },
                    {
                        "id": str(200 + i), "homeAway": "away",
                        "team": {"id": str(200 + i), "abbreviation": f"AW{i}",
                                 "displayName": f"Away Team {i}"},
                        "curatedRank": {"current": 99},
                        "records": [{"summary": "25-25"}],
                    },
                ],
                "venue": {"fullName": "Test Arena", "address": {}},
            }],
        }
        for i in range(8)
    ]
}


class _FakeResponse:
    """Minimal requests.Response stand-in."""
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


def _fake_cached_request(url, params=None, timeout=10, headers=None):
    """Return scoreboard data for ESPN URLs, empty dict otherwise."""
    if "espn.com" in url:
        if "scoreboard" in url:
            return _SCOREBOARD
        return {"items": [], "resultSets": [], "team": {}, "athletes": []}
    return {}


def _fake_requests_get(url, **kwargs):
    """Return synthetic BallDontLie player data."""
    if "balldontlie" in url:
        if "players" in url:
            return _FakeResponse({"data": [{"id": 12345, "first_name": "Test", "last_name": "Player"}]})
        if "stats" in url:
            return _FakeResponse({"data": [
                {"pts": 22, "reb": 5, "ast": 6, "min": "34:00",
                 "game": {"date": "2026-03-10T00:00:00Z"}}
            ]})
    return _FakeResponse({})


# Apply runtime patches for HTTP calls
_patches = [
    mock.patch("api_cache._cached_request", side_effect=_fake_cached_request),
    mock.patch("api_cache.requests.get", side_effect=_fake_requests_get),
    mock.patch("api_players.requests.get", side_effect=_fake_requests_get),
    mock.patch("threading.Thread.start", _guarded_thread_start),
]

for p in _patches:
    p.start()

# Patch api_client._cached_request AFTER importing api_client (it re-imports from api_cache)
import api_client
api_client._cached_request = _fake_cached_request

# Now safe to import the Flask app
from app import app

# Use port 5055 to avoid conflicts with any running dev server on 5000
MOCK_PORT = int(os.environ.get("MOCK_PORT", 5055))

if __name__ == "__main__":
    # Restore thread.start so Flask's own threads work
    import threading
    threading.Thread.start = _real_thread_start

    print(f"Starting mock server on http://localhost:{MOCK_PORT}")
    print(f"Use Locust to load test: python -m locust -f locustfile.py -H http://localhost:{MOCK_PORT}")
    print("Open http://localhost:8089 in browser for Locust UI")
    app.run(host="0.0.0.0", port=MOCK_PORT, debug=False, use_reloader=False)
