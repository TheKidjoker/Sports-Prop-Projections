"""
Background scan cache — keeps game analysis pre-computed for instant page loads.

- On demand: scans a sport when first requested by a visitor
- Every hour: refreshes all cached sports
- Daily at 6 AM EST: pre-scans all sports so data is ready for the day
- On visitor arrival (/api/games): triggers immediate refresh for that sport
- /api/scan returns cached results instantly, queues background refresh
"""

import threading
import time
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_cache = {}            # sport -> {"results": list, "ts": float}
_cache_lock = threading.Lock()

_queue = []            # sports queued for priority refresh
_queue_lock = threading.Lock()
_wake = threading.Event()
_started = False

BG_INTERVAL = 3600     # 1 hour between periodic full refreshes
ALL_SPORTS = ("nba", "nhl", "cbb", "cfb", "nfl")

DAILY_REFRESH_HOUR = 6  # 6 AM EST
EST = timezone(timedelta(hours=-5))


def init():
    """Start background refresh daemon. Safe to call multiple times."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="scan-cache").start()
    logger.info("[scan_cache] Background refresh thread started")


def get(sport):
    """Return (results, age_seconds) or (None, None)."""
    with _cache_lock:
        e = _cache.get(sport)
        if e is None:
            return None, None
        return e["results"], time.time() - e["ts"]


def put(sport, results):
    """Store results in cache."""
    with _cache_lock:
        _cache[sport] = {"results": results, "ts": time.time()}


def request_refresh(*sports):
    """Queue sports for immediate background refresh and wake the thread."""
    with _queue_lock:
        for s in sports:
            if s not in _queue:
                _queue.append(s)
    _wake.set()


def _scan(sport):
    """Run scan_all_games, cache results, sync to pick curation."""
    from game_scanner import scan_all_games
    import pick_curation
    try:
        results = scan_all_games(sport)
        put(sport, results)
        try:
            pick_curation.sync_picks_from_scan(results, sport)
        except Exception:
            pass
        logger.info("[scan_cache] Refreshed %s: %d games", sport, len(results))
        return results
    except Exception as e:
        logger.warning("[scan_cache] %s scan failed: %s", sport, e)
        return None


def _seconds_until_next_daily():
    """Return seconds until the next 6 AM EST."""
    now = datetime.now(EST)
    target = now.replace(hour=DAILY_REFRESH_HOUR, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _loop():
    """Background: refresh on demand, periodically, and daily at 6 AM EST."""
    next_daily = time.monotonic() + _seconds_until_next_daily()

    while True:
        wait_time = min(BG_INTERVAL, max(0, next_daily - time.monotonic()))
        _wake.wait(timeout=wait_time)
        _wake.clear()

        # Drain priority queue first
        while True:
            with _queue_lock:
                if not _queue:
                    break
                sport = _queue.pop(0)
            _scan(sport)

        # Daily 6 AM EST: pre-scan all sports for the day
        if time.monotonic() >= next_daily:
            logger.info("[scan_cache] Daily 6 AM EST refresh — scanning all sports")
            for sport in ALL_SPORTS:
                _scan(sport)
            next_daily = time.monotonic() + _seconds_until_next_daily()
            continue  # skip hourly refresh since we just did everything

        # Periodic: refresh everything that has been cached
        with _cache_lock:
            sports = list(_cache.keys())
        for sport in sports:
            _scan(sport)
