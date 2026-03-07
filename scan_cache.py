"""
Background scan cache — keeps game analysis pre-computed for instant page loads.

- On demand: scans a sport when first requested by a visitor
- Every hour: refreshes all cached sports
- Daily at 6 AM EST: pre-scans all sports so data is ready for the day
- On visitor arrival (/api/games): triggers immediate refresh for that sport
- /api/scan returns cached results instantly, queues background refresh
- Two-tier cache: in-memory for speed + Supabase for persistence across deploys
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

BG_INTERVAL = 3600     # 1 hour between periodic full refreshes
ALL_SPORTS = ("nba", "nhl", "cbb", "cfb", "nfl")

DAILY_REFRESH_HOUR = 6  # 6 AM EST
EST = timezone(timedelta(hours=-5))


STAGGER_DELAY = 15   # seconds between sport scan pairs to avoid rate limit bursts
SCAN_PARALLEL = 2    # scan this many sports concurrently

# File lock to prevent duplicate scan threads across gunicorn workers
_LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".scan_cache_lock")


def init():
    """Start background refresh daemon. Safe to call multiple times.
    Uses a file lock so only one gunicorn worker runs the scan thread.
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
        # Another worker already owns the scan thread — check if still alive
        try:
            with open(_LOCK_FILE, "r") as f:
                pid = int(f.read().strip())
            # On Unix, os.kill(pid, 0) checks if process exists
            # On Windows, this will raise an error if the process doesn't exist
            os.kill(pid, 0)
            logger.info("[scan_cache] Scan thread owned by worker pid=%d, skipping", pid)
            _started = True  # Don't retry
            return
        except (OSError, ValueError):
            # Stale lock file — reclaim it
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
    # Queue all sports for immediate warm-up on startup
    request_refresh(*ALL_SPORTS)
    logger.info("[scan_cache] Background thread started (pid=%d), queued startup warm-up", os.getpid())


def get(sport):
    """
    Return (results, age_seconds) or (None, None).
    Checks in-memory cache first, then Supabase persistent cache.
    """
    # Check in-memory first (fastest)
    with _cache_lock:
        e = _cache.get(sport)
        if e is not None:
            return e["results"], time.time() - e["ts"]

    # Check persistent Supabase cache
    db_results = cache_manager.get_cached_scan(sport, cache_minutes=60)
    if db_results:
        # Warm in-memory cache with DB data
        with _cache_lock:
            _cache[sport] = {"results": db_results, "ts": time.time()}
        logger.info("[scan_cache] Warmed memory from DB: %s", sport)
        return db_results, 0  # Treat as fresh since we just loaded it

    return None, None


def put(sport, results):
    """
    Store results in cache (both memory and persistent DB).
    """
    # Write to in-memory cache
    with _cache_lock:
        _cache[sport] = {"results": results, "ts": time.time()}

    # Write to persistent Supabase cache (async, don't block on errors)
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


def _scan(sport):
    """Run scan_all_games, cache results, sync to pick curation, fetch closing lines."""
    from game_scanner import scan_all_games
    import pick_curation
    try:
        results = scan_all_games(sport)
        put(sport, results)
        try:
            pick_curation.sync_picks_from_scan(results, sport)
        except Exception:
            pass
        # Progressively capture closing lines as games approach
        try:
            import tracker
            cl_result = tracker.fetch_closing_lines(sport)
            cl_updated = cl_result.get("updated", 0) if cl_result else 0
            if cl_updated > 0:
                logger.info("[scan_cache] Close lines for %s: %d updated", sport, cl_updated)
        except Exception:
            pass
        # Fetch closing lines for tracked bets (bet_tracker)
        try:
            import bet_tracker
            bet_tracker.fetch_closing_lines_for_bets(sport)
        except Exception:
            pass
        logger.info("[scan_cache] Refreshed %s: %d games", sport, len(results))
        return results
    except Exception as e:
        logger.warning("[scan_cache] %s scan failed: %s", sport, e)
        return None


def _scan_sports_parallel(sports):
    """Scan multiple sports in parallel batches of SCAN_PARALLEL with stagger between batches."""
    from concurrent.futures import ThreadPoolExecutor
    for i in range(0, len(sports), SCAN_PARALLEL):
        batch = sports[i:i + SCAN_PARALLEL]
        if len(batch) == 1:
            _scan(batch[0])
        else:
            with ThreadPoolExecutor(max_workers=SCAN_PARALLEL) as pool:
                list(pool.map(_scan, batch))
        # Stagger between batches (not after the last one)
        if i + SCAN_PARALLEL < len(sports):
            time.sleep(STAGGER_DELAY)


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
            _scan_sports_parallel(list(ALL_SPORTS))
            # Auto-grade all tracked bets after daily scan
            try:
                import bet_tracker
                bet_tracker.grade_all_tracked_bets()
            except Exception:
                pass
            next_daily = time.monotonic() + _seconds_until_next_daily()
            continue  # skip hourly refresh since we just did everything

        # Periodic: refresh all sports every hour (2 at a time)
        _scan_sports_parallel(list(ALL_SPORTS))
        # Auto-grade after hourly refresh to catch late-finishing games
        try:
            import bet_tracker
            bet_tracker.grade_all_tracked_bets()
        except Exception:
            pass
        # Cleanup old DB cache entries (keep last 24 hours)
        try:
            cache_manager.clear_old_cache_entries(hours=24)
        except Exception:
            pass
