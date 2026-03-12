"""
Stress tests for scan_cache:
- 50-thread interleaved get/put
- 5-sport concurrent access
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

import scan_cache


# ─── Test 1: 50-thread interleaved get/put ────────────────────────────────────
@pytest.mark.timeout(15, method="thread")
def test_interleaved_get_put():
    """50 threads doing interleaved get+put on same sport — no exceptions."""
    errors = []

    def _worker(tid):
        try:
            for i in range(100):
                # Alternate between get and put
                if i % 2 == 0:
                    scan_cache.put("nba", [{"game": tid, "iter": i}])
                else:
                    results, age = scan_cache.get("nba")
                    # Results might be None on first call or from another thread
                    if results is not None:
                        assert isinstance(results, list)
        except Exception as e:
            errors.append((tid, e))

    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(_worker, tid) for tid in range(50)]
        for f in futures:
            f.result()

    assert len(errors) == 0, f"Errors during interleaved get/put: {errors}"

    # Final state should have nba in cache with valid data
    results, age = scan_cache.get("nba")
    assert results is not None
    assert isinstance(results, list)


# ─── Test 2: 5-sport concurrent access ───────────────────────────────────────
@pytest.mark.timeout(15, method="thread")
def test_5_sport_concurrent():
    """5 threads × 100 cycles, each on different sport — all 5 in cache."""
    sports = ["nba", "nhl", "cbb", "cfb", "nfl"]
    errors = []

    def _worker(sport):
        try:
            for i in range(100):
                scan_cache.put(sport, [{"sport": sport, "cycle": i}])
                results, age = scan_cache.get(sport)
                assert results is not None
                assert isinstance(results, list)
        except Exception as e:
            errors.append((sport, e))

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(_worker, s) for s in sports]
        for f in futures:
            f.result()

    assert len(errors) == 0, f"Errors during 5-sport concurrent: {errors}"

    # All 5 sports should be in cache
    for sport in sports:
        results, age = scan_cache.get(sport)
        assert results is not None, f"{sport} missing from cache"
        assert isinstance(results, list)
        assert len(results) > 0
