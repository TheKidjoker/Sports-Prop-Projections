"""
Background scan cache — keeps game analysis pre-computed for instant page loads.

- On startup: pre-scans all sports to populate cache
- Every hour: refreshes all cached sports
- On visitor arrival (/api/games): triggers immediate refresh for that sport
- /api/scan returns cached results instantly, queues background refresh
"""

import threading
import time
import logging

logger = logging.getLogger(__name__)

_cache = {}            # sport -> {"results": list, "ts": float}
_cache_lock = threading.Lock()

_queue = []            # sports queued for priority refresh
_queue_lock = threading.Lock()
_wake = threading.Event()
_started = False

BG_INTERVAL = 3600     # 1 hour between periodic full refreshes
ALL_SPORTS = ("nba", "nhl", "cbb", "cfb", "nfl")


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
    """Run scan_all_games, cache results, save to tracker."""
    from game_scanner import scan_all_games
    import tracker
    try:
        results = scan_all_games(sport)
        put(sport, results)
        try:
            tracker.save_predictions(results, sport)
        except Exception:
            pass
        logger.info("[scan_cache] Refreshed %s: %d games", sport, len(results))
        return results
    except Exception as e:
        logger.warning("[scan_cache] %s scan failed: %s", sport, e)
        return None


def _loop():
    """Background: warm up all sports, then refresh on demand or periodically."""
    # Startup warm-up
    for sport in ALL_SPORTS:
        _scan(sport)
    logger.info("[scan_cache] Startup warm-up complete")

    while True:
        _wake.wait(timeout=BG_INTERVAL)
        _wake.clear()

        # Drain priority queue first
        while True:
            with _queue_lock:
                if not _queue:
                    break
                sport = _queue.pop(0)
            _scan(sport)

        # Periodic: refresh everything that has been cached
        with _cache_lock:
            sports = list(_cache.keys())
        for sport in sports:
            _scan(sport)
