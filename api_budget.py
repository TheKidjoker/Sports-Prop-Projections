"""
Daily API call budget tracker for The Odds API (500 calls/month free tier).

Tracks usage per calendar day in a JSON file. Hard-stops API calls when
the daily budget is exhausted to prevent burning through the monthly allocation.

Budget math: 500 calls/month / 30 days ~ 16 calls/day.
Default limit is 18/day for some flexibility while staying under 500/month.
"""

import os
import json
import threading
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_BUDGET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".odds_api_budget.json")

DAILY_LIMIT = int(os.environ.get("ODDS_API_DAILY_LIMIT", "18"))


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load():
    try:
        with open(_BUDGET_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save(data):
    try:
        with open(_BUDGET_FILE, "w") as f:
            json.dump(data, f)
    except OSError:
        pass


def record_call(count=1):
    """Record API call(s) for today. Returns new total for today."""
    with _lock:
        data = _load()
        today = _today()
        data[today] = data.get(today, 0) + count
        # Keep only last 31 days
        keys = sorted(data.keys())
        if len(keys) > 31:
            for k in keys[:-31]:
                del data[k]
        _save(data)
        total = data[today]
        logger.info("[budget] Recorded %d call(s) — today: %d/%d", count, total, DAILY_LIMIT)
        return total


def check_budget():
    """Return True if we still have budget remaining for today."""
    with _lock:
        data = _load()
        today = _today()
        used = data.get(today, 0)
        return used < DAILY_LIMIT


def get_usage():
    """Return current usage stats for the API and frontend."""
    with _lock:
        data = _load()
        today = _today()
        used_today = data.get(today, 0)
        used_month = sum(data.values())
        return {
            "used_today": used_today,
            "daily_limit": DAILY_LIMIT,
            "remaining_today": max(0, DAILY_LIMIT - used_today),
            "used_this_period": used_month,
            "monthly_limit": 500,
        }
