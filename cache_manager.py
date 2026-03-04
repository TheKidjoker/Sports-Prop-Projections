"""
Persistent cache layer using Supabase for scan results and props.
Survives deploys and benefits all users.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

# Lazy import to avoid circular dependencies
_supabase_client = None


def _get_supabase():
    """Lazy init Supabase client."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    from supabase import create_client
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")

    if not url or not key:
        print("[cache_manager] Supabase not configured, cache disabled", flush=True)
        return None

    try:
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception as e:
        print(f"[cache_manager] Supabase init failed: {e}", flush=True)
        return None


def get_cached_scan(sport: str, cache_minutes: int = 10) -> Optional[list]:
    """
    Get cached scan results from Supabase if recent enough.

    Args:
        sport: Sport key (nba, nhl, cbb, etc)
        cache_minutes: Max age in minutes

    Returns:
        Cached scan results or None
    """
    supabase = _get_supabase()
    if not supabase:
        return None

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cache_minutes)
        result = (
            supabase.table("scan_cache")
            .select("*")
            .eq("sport", sport)
            .gte("created_at", cutoff.isoformat())
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            print(f"[cache_manager] Cache HIT for scan:{sport}", flush=True)
            return json.loads(result.data[0]["results"])

        print(f"[cache_manager] Cache MISS for scan:{sport}", flush=True)
        return None
    except Exception as e:
        print(f"[cache_manager] get_cached_scan error: {e}", flush=True)
        return None


def cache_scan(sport: str, results: list) -> bool:
    """
    Store scan results in Supabase cache.

    Args:
        sport: Sport key
        results: Scan results to cache

    Returns:
        True if cached successfully
    """
    supabase = _get_supabase()
    if not supabase:
        return False

    try:
        supabase.table("scan_cache").insert({
            "sport": sport,
            "results": json.dumps(results),
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        print(f"[cache_manager] Cached scan:{sport}", flush=True)
        return True
    except Exception as e:
        print(f"[cache_manager] cache_scan error: {e}", flush=True)
        return False


def get_cached_props(sport: str, cache_minutes: int = 10) -> Optional[list]:
    """
    Get cached props from Supabase if recent enough.

    Args:
        sport: Sport key (nba, cbb)
        cache_minutes: Max age in minutes

    Returns:
        Cached props or None
    """
    supabase = _get_supabase()
    if not supabase:
        return None

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cache_minutes)
        result = (
            supabase.table("props_cache")
            .select("*")
            .eq("sport", sport)
            .gte("created_at", cutoff.isoformat())
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

        if result.data:
            print(f"[cache_manager] Cache HIT for props:{sport}", flush=True)
            return json.loads(result.data[0]["results"])

        print(f"[cache_manager] Cache MISS for props:{sport}", flush=True)
        return None
    except Exception as e:
        print(f"[cache_manager] get_cached_props error: {e}", flush=True)
        return None


def cache_props(sport: str, results: list) -> bool:
    """
    Store props in Supabase cache.

    Args:
        sport: Sport key
        results: Props to cache

    Returns:
        True if cached successfully
    """
    supabase = _get_supabase()
    if not supabase:
        return False

    try:
        supabase.table("props_cache").insert({
            "sport": sport,
            "results": json.dumps(results),
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
        print(f"[cache_manager] Cached props:{sport}", flush=True)
        return True
    except Exception as e:
        print(f"[cache_manager] cache_props error: {e}", flush=True)
        return False


def clear_old_cache_entries(hours: int = 24):
    """
    Delete cache entries older than X hours to prevent bloat.
    Run this periodically via background job.

    Args:
        hours: Delete entries older than this
    """
    supabase = _get_supabase()
    if not supabase:
        return

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Clean scan_cache
        supabase.table("scan_cache").delete().lt("created_at", cutoff.isoformat()).execute()

        # Clean props_cache
        supabase.table("props_cache").delete().lt("created_at", cutoff.isoformat()).execute()

        print(f"[cache_manager] Cleaned cache entries older than {hours}h", flush=True)
    except Exception as e:
        print(f"[cache_manager] clear_old_cache_entries error: {e}", flush=True)
