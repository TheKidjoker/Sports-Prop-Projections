"""
PRISM Player Prop Projection Engine

Pure calculation module — no API calls. All data passed as arguments.
Combines weighted projection formula with slot classification to surface
high-edge player prop signals.
"""

import math

# League average constants (updated once per season)
LEAGUE_AVG_TOTALS = {"nba": 224.0}
LEAGUE_AVG_DEF = {"nba": 112.0}


def calculate_prism_projection(season_avg, recent_games, stat_type,
                               opponent_def_rating, league_avg_def,
                               game_total, is_b2b, is_home, spread,
                               injured_teammates, posted_line, slot_type,
                               sport="nba"):
    """
    Core PRISM projection for a single player + stat type.

    Args:
        season_avg: float — season average for stat_type (e.g. ppg)
        recent_games: list of dicts — [{pts, reb, ast, min, date}, ...]
        stat_type: "pts" | "reb" | "ast"
        opponent_def_rating: float — opponent pts allowed per game (or None)
        league_avg_def: float — league average pts allowed
        game_total: float — over/under total for the game (or None)
        is_b2b: bool — back-to-back game
        is_home: bool — home game
        spread: float — current spread (or None)
        injured_teammates: list of dicts — [{name, ppg}, ...] star teammates OUT
        posted_line: float — sportsbook line for this prop (or None)
        slot_type: "public" | "vegas" | "unknown"
        sport: sport key

    Returns:
        dict with projection, edge, signal, confidence, streak, minutes_volatility
        or None if insufficient data
    """
    if season_avg is None or season_avg <= 0:
        return None

    league_total = LEAGUE_AVG_TOTALS.get(sport, 224.0)
    if league_avg_def is None or league_avg_def <= 0:
        league_avg_def = LEAGUE_AVG_DEF.get(sport, 112.0)

    # ── 1. Weighted Average ──
    stat_key = _stat_key(stat_type)
    valid_recent = [g for g in (recent_games or []) if g.get("min", 0) >= 15]

    if len(valid_recent) >= 3:
        recent_vals = [g.get(stat_key, 0) for g in valid_recent[:5]]
        recent_avg = sum(recent_vals) / len(recent_vals)
        weighted_avg = (recent_avg * 0.60) + (season_avg * 0.40)
    else:
        weighted_avg = season_avg

    # ── 2. Matchup Multiplier ──
    if opponent_def_rating and league_avg_def:
        matchup_mult = opponent_def_rating / league_avg_def
        matchup_mult = max(0.85, min(1.20, matchup_mult))
        matchup_available = True
    else:
        matchup_mult = 1.0
        matchup_available = False

    # ── 3. Pace Factor ──
    if game_total and game_total > 0:
        pace_factor = game_total / league_total
        pace_factor = max(0.90, min(1.15, pace_factor))
    else:
        pace_factor = 1.0

    # ── 4. Rest Factor ──
    rest_factor = 0.93 if is_b2b else 1.0

    # ── 5. Home/Away Adjustment ──
    home_away_adj = 1.03 if is_home else 0.98

    # ── 6. Blowout Discount ──
    blowout_disc = 0.88 if (spread is not None and abs(spread) > 10) else 1.0

    # ── 7. Injury Usage Boost (points only) ──
    usage_boost = 0.0
    if stat_type == "pts" and injured_teammates:
        total_lost_ppg = sum(t.get("ppg", 0) for t in injured_teammates)
        # Redistribute 60% across top remaining players (flat share)
        usage_boost = (total_lost_ppg * 0.60) / 3.0  # Assume ~3 top players absorb

    projection = (weighted_avg * matchup_mult * pace_factor *
                  rest_factor * home_away_adj * blowout_disc) + usage_boost
    projection = round(projection, 1)

    # ── Edge calculation ──
    line = posted_line
    if line is None:
        line = estimate_line_from_average(season_avg)
    if line is None or line <= 0:
        return None

    edge = round(projection - line, 1)

    # ── Slot integration ──
    signal = _apply_slot_integration(edge, slot_type)

    # ── Streak detection ──
    streak = detect_streak(recent_games or [], line, stat_type)

    # ── Minutes volatility ──
    min_stdev, is_unstable = calculate_minutes_volatility(recent_games or [])

    # ── Confidence ──
    confidence = _calculate_confidence(
        edge, len(valid_recent), matchup_available,
        streak, is_unstable,
    )

    return {
        "projection": projection,
        "line": round(line, 1),
        "edge": edge,
        "signal": signal,
        "confidence": confidence,
        "streak": streak,
        "minutes_stdev": round(min_stdev, 1) if min_stdev else None,
        "minutes_unstable": is_unstable,
    }


def _apply_slot_integration(edge, slot_type):
    """
    Combine PRISM edge direction with slot type for signal strength.

    Vegas slot + under = STRONG UNDER (line inflated for public action)
    Public slot + over = STRONG OVER (math and momentum agree)
    """
    abs_edge = abs(edge)

    if abs_edge < 1.0:
        return "PASS"

    is_over = edge > 0

    if abs_edge >= 2.0:
        if slot_type in ("vegas", "trap"):
            if not is_over:
                return "STRONG UNDER"
            else:
                return "SKIP"
        elif slot_type in ("public", "caution"):
            if is_over:
                return "STRONG OVER"
            else:
                return "LEAN UNDER"
        else:
            return "LEAN OVER" if is_over else "LEAN UNDER"
    else:
        # 1-2 pt edge
        return "LEAN OVER" if is_over else "LEAN UNDER"


def detect_streak(recent_games, line, stat_type):
    """
    Detects if 4+ of last 5 games went in the same direction vs the line.

    Returns:
        dict {direction: "OVER"/"UNDER", count: int} or None
    """
    if not recent_games or len(recent_games) < 5:
        return None

    stat_key = _stat_key(stat_type)
    last_5 = recent_games[:5]

    over_count = sum(1 for g in last_5 if g.get(stat_key, 0) > line)
    under_count = sum(1 for g in last_5 if g.get(stat_key, 0) < line)

    if over_count >= 4:
        return {"direction": "OVER", "count": over_count}
    elif under_count >= 4:
        return {"direction": "UNDER", "count": under_count}

    return None


def calculate_minutes_volatility(recent_games):
    """
    Standard deviation of minutes played. If stdev > 5, flag as unstable.

    Returns:
        (stdev: float, is_unstable: bool)
    """
    if not recent_games or len(recent_games) < 3:
        return 0.0, False

    minutes = [g.get("min", 0) for g in recent_games[:7] if g.get("min", 0) > 0]

    if len(minutes) < 3:
        return 0.0, False

    mean = sum(minutes) / len(minutes)
    variance = sum((m - mean) ** 2 for m in minutes) / len(minutes)
    stdev = math.sqrt(variance)

    return stdev, stdev > 5.0


def estimate_line_from_average(season_avg):
    """
    Tier 2 fallback when no Odds API key: estimated line from season average.
    Books typically set lines slightly below the average.
    """
    if season_avg is None or season_avg <= 0:
        return None
    return round(season_avg * 0.97, 1)


def _calculate_confidence(edge, num_recent_games, matchup_available,
                          streak, is_unstable):
    """
    Confidence score 0-100 based on edge magnitude and data quality.
    """
    abs_edge = abs(edge)

    # Base from edge magnitude
    if abs_edge >= 4:
        base = 85
    elif abs_edge >= 3:
        base = 75
    elif abs_edge >= 2:
        base = 65
    elif abs_edge >= 1:
        base = 50
    else:
        base = 30

    # Data quality: how many recent games available
    if num_recent_games >= 5:
        base += 5
    elif num_recent_games < 3:
        base -= 10

    # Matchup data
    if matchup_available:
        base += 5

    # Streak
    if streak:
        base += 5

    # Minutes instability
    if is_unstable:
        base -= 10

    return max(10, min(95, base))


def _stat_key(stat_type):
    """Map stat_type to game log dict key."""
    return {"pts": "pts", "reb": "reb", "ast": "ast"}.get(stat_type, "pts")


def get_league_defensive_average(sport="nba"):
    """Simple lookup for league average points allowed."""
    return LEAGUE_AVG_DEF.get(sport, 112.0)
