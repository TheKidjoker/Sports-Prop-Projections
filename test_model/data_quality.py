"""
Data Quality Report — completeness stats, feature drift detection,
and API freshness monitoring for historical game data.
"""

import math
import logging
from datetime import datetime, date

from test_model import db as tm_db

logger = logging.getLogger(__name__)


def nba_data_quality_report():
    """
    Return completeness stats for NBA historical data:
    total_games, games_with_spread, games_with_opening, games_with_ou,
    games_with_venue, games_per_season, date_coverage_pct, games_with_pinnacle.
    """
    return _data_quality_report("nba")


def _data_quality_report(sport):
    """Generic data quality report for any sport."""
    games = tm_db.get_historical_games(sport)
    total = len(games)

    if total == 0:
        return {
            "sport": sport,
            "total_games": 0,
            "games_with_spread": 0,
            "games_with_opening": 0,
            "games_with_ou": 0,
            "games_with_venue": 0,
            "games_with_pinnacle": 0,
            "games_final": 0,
            "games_per_season": {},
            "date_range": None,
        }

    with_spread = sum(1 for g in games if g.get("closing_spread") is not None)
    with_opening = sum(1 for g in games if g.get("opening_spread") is not None)
    with_ou = sum(1 for g in games if g.get("over_under") is not None)
    with_venue = sum(1 for g in games if g.get("venue_name"))
    with_pinnacle = sum(1 for g in games if g.get("pinnacle_spread") is not None)
    games_final = sum(1 for g in games if g.get("game_status") == "STATUS_FINAL")

    # Group by season (approximate: use year from game_date)
    by_season = {}
    for g in games:
        gd = g.get("game_date", "")[:7]  # "YYYY-MM"
        if len(gd) >= 7:
            month = int(gd[5:7])
            year = int(gd[:4])
            # NBA season spans Oct-Apr: Oct 2024 = 2024-25 season
            season = f"{year}-{str(year + 1)[-2:]}" if month >= 10 else f"{year - 1}-{str(year)[-2:]}"
            by_season[season] = by_season.get(season, 0) + 1

    dates = sorted(g.get("game_date", "") for g in games if g.get("game_date"))
    date_range = {"earliest": dates[0], "latest": dates[-1]} if dates else None

    return {
        "sport": sport,
        "total_games": total,
        "games_with_spread": with_spread,
        "games_with_opening": with_opening,
        "games_with_ou": with_ou,
        "games_with_venue": with_venue,
        "games_with_pinnacle": with_pinnacle,
        "games_final": games_final,
        "games_per_season": by_season,
        "date_range": date_range,
        "completeness": {
            "spread_pct": round(with_spread / total * 100, 1) if total > 0 else 0,
            "opening_pct": round(with_opening / total * 100, 1) if total > 0 else 0,
            "ou_pct": round(with_ou / total * 100, 1) if total > 0 else 0,
            "venue_pct": round(with_venue / total * 100, 1) if total > 0 else 0,
            "pinnacle_pct": round(with_pinnacle / total * 100, 1) if total > 0 else 0,
        },
    }


# ─── Feature Drift Detection ────────────────────────────────────────────────

def detect_feature_drift(sport, recent_window=50):
    """
    Compare feature distributions between recent games and historical baseline.

    Uses a simple mean/stddev comparison: if the recent window's mean deviates
    from the historical mean by more than 1.5 standard deviations, flag drift.

    Args:
        sport: sport key
        recent_window: number of most recent games to compare

    Returns:
        dict with per-feature drift flags and overall health score
    """
    from test_model.features import FEATURE_COLUMNS, _extract_features_from_state

    games = tm_db.get_historical_games(sport)
    if len(games) < recent_window * 2:
        return {
            "sport": sport,
            "status": "insufficient_data",
            "total_games": len(games),
            "required": recent_window * 2,
            "drifted_features": [],
        }

    # Sort chronologically
    games.sort(key=lambda g: g.get("game_date", ""))

    # Extract feature values for numeric columns that are meaningful to monitor
    # Focus on key spread/scoring/Elo features
    monitor_features = [
        "closing_spread", "spread_abs", "line_movement_abs",
        "home_scoring_avg_5", "away_scoring_avg_5",
        "home_def_avg_5", "away_def_avg_5",
        "elo_diff", "rank_diff",
    ]

    historical = games[:-recent_window]
    recent = games[-recent_window:]

    drifted = []
    feature_stats = {}

    for feat in monitor_features:
        hist_vals = _extract_field_values(historical, feat)
        recent_vals = _extract_field_values(recent, feat)

        if not hist_vals or not recent_vals:
            continue

        hist_mean = sum(hist_vals) / len(hist_vals)
        hist_std = _stddev(hist_vals, hist_mean)

        recent_mean = sum(recent_vals) / len(recent_vals)

        # Z-score of recent mean vs historical distribution
        z_score = abs(recent_mean - hist_mean) / hist_std if hist_std > 0 else 0

        is_drifted = z_score > 1.5
        severity = "high" if z_score > 2.5 else "moderate" if z_score > 1.5 else "normal"

        stat = {
            "feature": feat,
            "historical_mean": round(hist_mean, 3),
            "recent_mean": round(recent_mean, 3),
            "historical_std": round(hist_std, 3),
            "z_score": round(z_score, 3),
            "severity": severity,
            "drifted": is_drifted,
        }
        feature_stats[feat] = stat

        if is_drifted:
            drifted.append(stat)

    health = "healthy" if not drifted else (
        "degraded" if len(drifted) <= 2 else "critical"
    )

    return {
        "sport": sport,
        "status": health,
        "total_games": len(games),
        "recent_window": recent_window,
        "drifted_features": drifted,
        "drifted_count": len(drifted),
        "monitored_count": len(feature_stats),
        "feature_stats": feature_stats,
    }


def _extract_field_values(games, field):
    """Pull numeric values for a field from game dicts."""
    vals = []
    for g in games:
        v = g.get(field)
        if v is not None:
            try:
                vals.append(float(v))
            except (ValueError, TypeError):
                continue
    return vals


def _stddev(values, mean):
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    return math.sqrt(variance)


# ─── API Freshness Monitor ──────────────────────────────────────────────────

def check_api_freshness():
    """
    Check the freshness of data from each API source.

    Returns:
        dict with per-source status (fresh/stale/unavailable)
    """
    sources = {}

    # Soccer API budget
    try:
        from api_soccer import get_budget_status, is_available
        budget = get_budget_status()
        sources["api_football"] = {
            "configured": is_available(),
            "calls_used": budget["calls_used"],
            "calls_remaining": budget["calls_remaining"],
            "status": "available" if is_available() else "not_configured",
        }
    except Exception:
        sources["api_football"] = {"status": "error"}

    # The Odds API
    try:
        import os
        odds_key = os.environ.get("ODDS_API_KEY", "")
        sources["odds_api"] = {
            "configured": bool(odds_key),
            "status": "available" if odds_key else "not_configured",
        }
    except Exception:
        sources["odds_api"] = {"status": "error"}

    # Odds.io API
    try:
        import os
        odds_io_key = os.environ.get("ODDS_API_IO_KEY", "")
        sources["odds_io"] = {
            "configured": bool(odds_io_key),
            "status": "available" if odds_io_key else "not_configured",
        }
    except Exception:
        sources["odds_io"] = {"status": "error"}

    # Supabase
    try:
        import os
        supa_url = os.environ.get("SUPABASE_URL", "")
        sources["supabase"] = {
            "configured": bool(supa_url),
            "status": "available" if supa_url else "not_configured",
        }
    except Exception:
        sources["supabase"] = {"status": "error"}

    # Historical data freshness per sport
    for sport in ["nba", "nhl", "nfl", "cfb", "cbb", "mlb"]:
        try:
            games = tm_db.get_historical_games(sport)
            if games:
                dates = [g.get("game_date", "") for g in games if g.get("game_date")]
                if dates:
                    latest = max(dates)
                    try:
                        latest_dt = datetime.strptime(latest[:10], "%Y-%m-%d").date()
                        days_old = (date.today() - latest_dt).days
                        status = "fresh" if days_old <= 7 else (
                            "stale" if days_old <= 30 else "very_stale"
                        )
                    except ValueError:
                        days_old = None
                        status = "unknown"

                    sources[f"historical_{sport}"] = {
                        "total_games": len(games),
                        "latest_date": latest[:10],
                        "days_since_update": days_old,
                        "status": status,
                    }
                else:
                    sources[f"historical_{sport}"] = {"total_games": len(games), "status": "no_dates"}
            else:
                sources[f"historical_{sport}"] = {"total_games": 0, "status": "empty"}
        except Exception:
            sources[f"historical_{sport}"] = {"status": "error"}

    return sources


def full_health_check(sports=None):
    """
    Comprehensive health check: data completeness, feature drift, API freshness.

    Args:
        sports: list of sport keys (default: all main sports)

    Returns:
        dict with overall health status and per-sport details
    """
    if sports is None:
        sports = ["nba", "nhl", "nfl", "cfb", "cbb", "mlb"]

    result = {
        "timestamp": datetime.now().isoformat(),
        "api_freshness": check_api_freshness(),
        "sports": {},
    }

    for sport in sports:
        sport_health = {}

        # Data completeness
        try:
            sport_health["completeness"] = _data_quality_report(sport)
        except Exception as e:
            sport_health["completeness"] = {"error": str(e)}

        # Feature drift
        try:
            sport_health["feature_drift"] = detect_feature_drift(sport)
        except Exception as e:
            sport_health["feature_drift"] = {"error": str(e)}

        result["sports"][sport] = sport_health

    # Overall status
    statuses = []
    for s, data in result["sports"].items():
        drift = data.get("feature_drift", {})
        if drift.get("status") == "critical":
            statuses.append("critical")
        elif drift.get("status") == "degraded":
            statuses.append("degraded")
        else:
            statuses.append("healthy")

    if "critical" in statuses:
        result["overall"] = "critical"
    elif "degraded" in statuses:
        result["overall"] = "degraded"
    else:
        result["overall"] = "healthy"

    return result
