"""
Background scan cache — keeps game analysis pre-computed for instant page loads.

API Budget Mode (500 calls/month free tier):
- Scans are ON-DEMAND only — triggered when a user requests a sport
- No automatic hourly refresh of all sports
- Daily 6 AM EST: refreshes only actively-used sports
- Persistent Supabase cache: 8-hour TTL (vs old 60-min)
- All Odds API calls go through api_cache with 4-hour TTL + daily budget
"""

import os
import threading
import time
import logging
from datetime import datetime, timedelta, timezone
import cache_manager

logger = logging.getLogger(__name__)

_cache = {}            # sport -> {"results": list, "ts": float}
_cache_lock = threading.Lock()

_queue = []            # sports queued for priority refresh
_queue_lock = threading.Lock()
_wake = threading.Event()
_started = False

ALL_SPORTS = ("nba", "nhl", "cbb", "cfb", "nfl", "mlb")

DAILY_REFRESH_HOUR = 6  # 6 AM EST
EST = timezone(timedelta(hours=-5))

STAGGER_DELAY = 15   # seconds between sport scan pairs
SCAN_PARALLEL = 2

# Persistent cache TTL — how long Supabase-cached results are considered valid
PERSISTENT_CACHE_MINUTES = 480  # 8 hours

# Minimum age (seconds) before a sport is eligible for background re-scan
STALE_THRESHOLD = 14400  # 4 hours — matches Odds API cache TTL

# File lock to prevent duplicate scan threads across gunicorn workers
_LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".scan_cache_lock")


def init():
    """Start background refresh daemon. Safe to call multiple times.
    Uses a file lock so only one gunicorn worker runs the scan thread.
    No startup warm-up — scans happen on-demand when users visit.
    """
    global _started
    if _started:
        return

    # Acquire file lock — only one worker wins
    try:
        fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
    except FileExistsError:
        try:
            with open(_LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            logger.info("[scan_cache] Scan thread owned by worker pid=%d, skipping", pid)
            _started = True
            return
        except (OSError, ValueError):
            try:
                os.unlink(_LOCK_FILE)
                fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, str(os.getpid()).encode())
                finally:
                    os.close(fd)
            except (FileExistsError, OSError):
                _started = True
                return

    import atexit
    atexit.register(lambda: os.unlink(_LOCK_FILE) if os.path.exists(_LOCK_FILE) else None)

    _started = True
    threading.Thread(target=_loop, daemon=True, name="scan-cache").start()
    logger.info("[scan_cache] Background thread started (pid=%d) — on-demand mode, no startup warm-up", os.getpid())


def get(sport):
    """
    Return (results, age_seconds) or (None, None).
    Checks in-memory cache first, then Supabase persistent cache (8-hour TTL).
    """
    with _cache_lock:
        e = _cache.get(sport)
        if e is not None:
            return e["results"], time.time() - e["ts"]

    db_results = cache_manager.get_cached_scan(sport, cache_minutes=PERSISTENT_CACHE_MINUTES)
    if db_results:
        with _cache_lock:
            _cache[sport] = {"results": db_results, "ts": time.time()}
        logger.info("[scan_cache] Warmed memory from DB: %s", sport)
        return db_results, 0

    return None, None


def put(sport, results):
    """Store results in cache (both memory and persistent DB)."""
    with _cache_lock:
        _cache[sport] = {"results": results, "ts": time.time()}

    try:
        cache_manager.cache_scan(sport, results)
    except Exception as e:
        logger.warning("[scan_cache] Failed to persist to DB: %s", e)


def request_refresh(*sports):
    """Queue sports for immediate background refresh and wake the thread."""
    with _queue_lock:
        for s in sports:
            if s not in _queue:
                _queue.append(s)
    _wake.set()


def request_refresh_if_stale(*sports):
    """Queue sports for refresh only if their cache is older than STALE_THRESHOLD.
    Prevents burning API calls when data is still fresh."""
    import api_budget
    if not api_budget.check_budget():
        logger.info("[scan_cache] Budget exhausted — skipping refresh request")
        return

    to_refresh = []
    for sport in sports:
        with _cache_lock:
            e = _cache.get(sport)
        if e is None or (time.time() - e["ts"]) > STALE_THRESHOLD:
            to_refresh.append(sport)

    if to_refresh:
        request_refresh(*to_refresh)


def _scan(sport):
    """Run scan_all_games and cache results. Lightweight — no props or closing lines."""
    import gc
    from game_scanner import scan_all_games
    import pick_curation

    # Check budget before scanning (scans make Odds API calls internally)
    import api_budget
    if not api_budget.check_budget():
        logger.warning("[scan_cache] Budget exhausted — skipping %s scan", sport)
        return None

    try:
        results = scan_all_games(sport)
        put(sport, results)
        try:
            pick_curation.sync_picks_from_scan(results, sport)
        except Exception:
            pass
        logger.info("[scan_cache] Refreshed %s: %d games", sport, len(results))
        gc.collect()
        return results
    except Exception as e:
        logger.warning("[scan_cache] %s scan failed: %s", sport, e)
        gc.collect()
        return None


def _seconds_until_next_daily():
    """Return seconds until the next 6 AM EST."""
    now = datetime.now(EST)
    target = now.replace(hour=DAILY_REFRESH_HOUR, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _loop():
    """Background: process on-demand queue + daily 6 AM refresh of active sports."""
    next_daily = time.monotonic() + _seconds_until_next_daily()

    while True:
        wait_time = max(0, next_daily - time.monotonic())
        _wake.wait(timeout=wait_time)
        _wake.clear()

        # Drain priority queue
        while True:
            with _queue_lock:
                if not _queue:
                    break
                sport = _queue.pop(0)
            _scan(sport)

        # Daily 6 AM EST: refresh only actively-cached sports (not all 6)
        if time.monotonic() >= next_daily:
            with _cache_lock:
                active_sports = list(_cache.keys())
            if active_sports:
                logger.info("[scan_cache] Daily 6 AM refresh for active sports: %s", active_sports)
                for sport in active_sports:
                    _scan(sport)
            # Auto-grade tracked bets
            try:
                import bet_tracker
                bet_tracker.grade_all_tracked_bets()
            except Exception:
                pass
            # Cleanup old DB cache entries
            try:
                cache_manager.clear_old_cache_entries(hours=24)
            except Exception:
                pass
            next_daily = time.monotonic() + _seconds_until_next_daily()
