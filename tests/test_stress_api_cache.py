"""
Stress tests for api_cache._cached_request:
- Lock contention under 100 concurrent threads
- Overflow eviction at CACHE_MAX_SIZE (500)
- Thundering herd on cached key
"""

import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, MagicMock

import pytest

import api_cache


class _FakeResponse:
    """Minimal requests.Response stand-in."""

    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


# ─── Test 1: 100-thread contention ───────────────────────────────────────────
@pytest.mark.timeout(30, method="thread")
def test_100_thread_contention():
    """100 threads × 50 iterations hitting ~10 URLs — no exceptions, cache <= 500."""
    call_count = {"n": 0}
    lock = threading.Lock()

    def _fake_get(url, **kwargs):
        with lock:
            call_count["n"] += 1
        return _FakeResponse({"url": url, "ok": True})

    with patch("api_cache.requests.get", side_effect=_fake_get):
        errors = []

        def _worker(tid):
            try:
                for i in range(50):
                    url = f"https://api.example.com/endpoint/{i % 10}"
                    result = api_cache._cached_request(url, params={"t": tid})
                    assert result is not None
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=100) as pool:
            futures = [pool.submit(_worker, tid) for tid in range(100)]
            for f in futures:
                f.result()

    assert len(errors) == 0, f"Errors during contention: {errors}"
    assert len(api_cache._cache) <= api_cache.CACHE_MAX_SIZE


# ─── Test 2: Overflow eviction at 500 ────────────────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_overflow_eviction():
    """Pre-fill 500 entries, insert 501st — oldest evicted, size stays 500."""
    now = time.time()

    # Pre-fill with timestamps so we know eviction order
    with api_cache._cache_lock:
        for i in range(500):
            key = f"https://fill.com/{i}|[]"
            api_cache._cache[key] = {"data": {"i": i}, "ts": now - (500 - i)}

    assert len(api_cache._cache) == 500

    # Insert 501st via _cached_request
    with patch("api_cache.requests.get", return_value=_FakeResponse({"new": True})):
        result = api_cache._cached_request("https://fill.com/new_entry")

    assert result == {"new": True}
    assert len(api_cache._cache) <= 500

    # The oldest entry (i=0, oldest timestamp) should be evicted
    oldest_key = "https://fill.com/0|[]"
    assert oldest_key not in api_cache._cache


# ─── Test 3: Thundering herd — cached key ────────────────────────────────────
@pytest.mark.timeout(10, method="thread")
def test_thundering_herd_cached():
    """100 threads reading a pre-cached key — requests.get never called."""
    cache_key = "https://cached.com/data|[]"
    with api_cache._cache_lock:
        api_cache._cache[cache_key] = {"data": {"cached": True}, "ts": time.time()}

    call_count = {"n": 0}

    def _should_not_call(url, **kwargs):
        call_count["n"] += 1
        return _FakeResponse({"cached": False})

    with patch("api_cache.requests.get", side_effect=_should_not_call):
        results = []

        def _reader(_):
            r = api_cache._cached_request("https://cached.com/data")
            results.append(r)

        with ThreadPoolExecutor(max_workers=100) as pool:
            list(pool.map(_reader, range(100)))

    assert call_count["n"] == 0, f"requests.get called {call_count['n']} times on cached data"
    assert all(r == {"cached": True} for r in results)
