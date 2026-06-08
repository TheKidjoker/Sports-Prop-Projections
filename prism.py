"""
PRISM Player Prop Projection Engine

Pure calculation module — no API calls. All data passed as arguments.
Combines weighted projection formula with slot classification to surface
high-edge player prop signals.
"""

import math
from constants import USE_DYNAMIC_PRISM_WEIGHTS, USE_ZSCORE_MATCHUP

# League average defaults (fallback if dynamic fetch fails)
LEAGUE_AVG_TOTALS = {"nba": 224.0, "nhl": 6.0, "mlb": 8.5}
LEAGUE_AVG_DEF = {"nba": 112.0, "nhl": 3.0, "mlb": 4.25}

# League averages for stat-specific matchup multipliers (hardcoded fallbacks)
_LEAGUE_AVG_STATS_DEFAULTS = {
    "nba": {"reb": 43.5, "steals": 7.5},
    "nhl": {"goals_allowed": 3.0, "shots_allowed": 30.0},
}

# League standard deviations for z-score matchup model (hardcoded fallbacks)
_LEAGUE_STDEV_DEFAULTS = {
    "nba": {"pts_allowed": 5.5, "reb": 3.2, "steals": 1.2},
    "nhl": {"goals_allowed": 0.6, "shots_allowed": 4.0},
    "mlb": {"runs_allowed": 1.2, "k_rate": 2.0},
}

# Z-score sensitivity per stat type (how much the matchup matters)
_ZSCORE_SENSITIVITY = {
    "pts": 0.04,
    "reb": 0.03,
    "ast": 0.025,
    "g": 0.04,
    "sog": 0.03,
    "k": 0.05,
    "h": 0.03,
    "tb": 0.035,
    "hr": 0.02,
    "rbi": 0.025,
    "er": 0.04,
    "ha": 0.035,
}

# Dynamic league averages cache for matchup stats
_league_matchup_avgs = {}
_league_matchup_ts = 0


def _get_league_matchup_avgs(sport="nba"):
    """Get league-wide matchup averages, cached 24 hours."""
    import time
    global _league_matchup_avgs, _league_matchup_ts
    now = time.time()
    if sport in _league_matchup_avgs and now - _league_matchup_ts < 86400:
        return _league_matchup_avgs[sport]
    try:
        from api_client import get_league_avg_stats
        avgs = get_league_avg_stats(sport)
        if sport == "nhl":
            if avgs and avgs.get("avgGoalsAllowed") and avgs.get("avgShotsAllowed"):
                result = {"goals_allowed": avgs["avgGoalsAllowed"], "shots_allowed": avgs["avgShotsAllowed"]}
                _league_matchup_avgs[sport] = result
                _league_matchup_ts = now
                return result
        else:
            if avgs and avgs.get("avgRebounds") and avgs.get("avgSteals"):
                result = {"reb": avgs["avgRebounds"], "steals": avgs["avgSteals"]}
                _league_matchup_avgs[sport] = result
                _league_matchup_ts = now
                return result
    except Exception:
        pass
    return _LEAGUE_AVG_STATS_DEFAULTS.get(sport, {})

# Dynamic league averages cache
_dynamic_avgs = {}
_dynamic_avgs_ts = 0


def _get_dynamic_league_avgs(sport="nba"):
    """Get league averages from historical DB, cached for 24 hours."""
    import time
    global _dynamic_avgs, _dynamic_avgs_ts
    now = time.time()
    cache_key = sport
    if cache_key in _dynamic_avgs and now - _dynamic_avgs_ts < 86400:
        return _dynamic_avgs[cache_key]
    try:
        from test_model import db as tm_db
        games = tm_db.get_historical_games(sport)
        if not games:
            return None
        # Use only current season games (last ~6 months)
        final_games = [g for g in games
                       if g.get("game_status") == "STATUS_FINAL"
                       and g.get("home_score") is not None
                       and g.get("away_score") is not None]
        if len(final_games) < 50:
            return None
        # Use most recent 500 games (approximately current season)
        recent = final_games[-500:]
        total_pts = sum(g["home_score"] + g["away_score"] for g in recent)
        avg_total = total_pts / len(recent)
        avg_def = avg_total / 2
        result = {"avg_total": round(avg_total, 1), "avg_def": round(avg_def, 1)}
        _dynamic_avgs[cache_key] = result
        _dynamic_avgs_ts = now
        return result
    except Exception:
        return None


def _compute_rest_factor(is_b2b, days_rest=None, sport="nba"):
    """
    Gradient rest factor based on days since last game.
    0 days (B2B): 0.93 | 1 day: 0.97 | 2 days: 1.0 | 3+ days: 1.02
    Falls back to binary B2B logic if days_rest not available.
    MLB: always 1.0 (162-game daily schedule, no rest effect).
    """
    if sport == "mlb":
        return 1.0
    if days_rest is not None:
        if days_rest <= 0:
            return 0.93
        elif days_rest == 1:
            return 0.97
        elif days_rest == 2:
            return 1.0
        else:
            return 1.02
    # Fallback: binary B2B
    return 0.93 if is_b2b else 1.0


def _compute_zscore_matchup(stat_type, sport, opponent_def_rating, league_avg_def,
                            opp, league_stats):
    """
    Z-score based matchup multiplier with soft tanh cap.
    z = (opp_value - league_avg) / league_stdev
    mult = 1.0 + z * sensitivity

    Returns:
        (matchup_mult, matchup_available) tuple
    """
    sensitivity = _ZSCORE_SENSITIVITY.get(stat_type, 0.03)
    stdev_defaults = _LEAGUE_STDEV_DEFAULTS.get(sport, {})

    opp_value = None
    league_avg = None
    league_stdev = None

    if stat_type == "pts":
        opp_value = opponent_def_rating
        league_avg = league_avg_def
        league_stdev = stdev_defaults.get("pts_allowed", 5.5)
    elif stat_type == "reb":
        opp_value = opp.get("avgRebounds")
        league_avg = league_stats.get("reb", 43.5)
        league_stdev = stdev_defaults.get("reb", 3.2)
        # Inverted: weak rebounder = positive z for player
        if opp_value and league_avg:
            opp_value = league_avg + (league_avg - opp_value)  # invert
    elif stat_type == "ast":
        opp_value = opp.get("avgSteals")
        league_avg = league_stats.get("steals", 7.5)
        league_stdev = stdev_defaults.get("steals", 1.2)
        # Inverted: more steals = worse for player
        if opp_value and league_avg:
            opp_value = league_avg + (league_avg - opp_value)
    elif stat_type == "g":
        opp_value = opponent_def_rating
        league_avg = league_avg_def
        league_stdev = stdev_defaults.get("goals_allowed", 0.6)
    elif stat_type == "sog":
        opp_value = opp.get("avgShotsAllowed")
        league_avg = league_stats.get("shots_allowed", 30.0)
        league_stdev = stdev_defaults.get("shots_allowed", 4.0)

    if opp_value is None or league_avg is None or league_stdev is None or league_stdev <= 0:
        return 1.0, False

    z = (opp_value - league_avg) / league_stdev

    # Soft cap via tanh at |z| > 2.0 (diminishing returns)
    if abs(z) > 2.0:
        z = 2.0 * math.tanh(z / 2.0)

    matchup_mult = 1.0 + z * sensitivity
    return matchup_mult, True


def calculate_prism_projection(season_avg, recent_games, stat_type,
                               opponent_def_rating, league_avg_def,
                               game_total, is_b2b, is_home, spread,
                               injured_teammates, posted_line, slot_type,
                               sport="nba", player_rank=0,
                               opponent_stats=None, days_rest=None):
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
        player_rank: int — 0/1/2 rank among team's top-3 scorers (for usage boost)

    Returns:
        dict with projection, edge, signal, confidence, streak, minutes_volatility,
        line_source, or None if insufficient data
    """
    if season_avg is None or season_avg <= 0:
        return None

    # Use dynamic league averages if available, fall back to hardcoded
    dynamic = _get_dynamic_league_avgs(sport)
    if dynamic:
        league_total = dynamic["avg_total"]
        if league_avg_def is None or league_avg_def <= 0:
            league_avg_def = dynamic["avg_def"]
    else:
        league_total = LEAGUE_AVG_TOTALS.get(sport, 224.0)
        if league_avg_def is None or league_avg_def <= 0:
            league_avg_def = LEAGUE_AVG_DEF.get(sport, 112.0)

    # ── 1. Weighted Average (dynamic weighting) ──
    stat_key = _stat_key(stat_type)
    if sport == "mlb":
        # MLB: no minutes filter — all games are valid
        valid_recent = list(recent_games or [])
    else:
        min_minutes = 10 if sport == "nhl" else 15
        valid_recent = [g for g in (recent_games or []) if g.get("min", 0) >= min_minutes]

    if len(valid_recent) >= 3:
        recent_vals = [g.get(stat_key, 0) for g in valid_recent[:10]]
        recent_avg = sum(recent_vals) / len(recent_vals)
        n_recent = len(recent_vals)

        if USE_DYNAMIC_PRISM_WEIGHTS:
            # Dynamic: weight adapts to sample size
            # prior_weights: nba=15, nhl=12, cbb=20
            prior_weights = {"nba": 15, "nhl": 12, "cbb": 20, "mlb": 18}
            prior_w = prior_weights.get(sport, 15)
            recent_weight = min(n_recent, 10) / (min(n_recent, 10) + prior_w)
            weighted_avg = (recent_avg * recent_weight) + (season_avg * (1.0 - recent_weight))
        else:
            # Legacy fixed 60/40
            weighted_avg = (recent_avg * 0.60) + (season_avg * 0.40)
    else:
        weighted_avg = season_avg

    # ── 2. Matchup Multiplier (z-score based or legacy ratio) ──
    league_stats = _get_league_matchup_avgs(sport)
    opp = opponent_stats or {}

    if USE_ZSCORE_MATCHUP:
        matchup_mult, matchup_available = _compute_zscore_matchup(
            stat_type, sport, opponent_def_rating, league_avg_def, opp, league_stats
        )
    else:
        # Legacy ratio-based matchup
        if stat_type == "pts":
            if opponent_def_rating and league_avg_def:
                matchup_mult = opponent_def_rating / league_avg_def
                matchup_mult = max(0.85, min(1.20, matchup_mult))
                matchup_available = True
            else:
                matchup_mult = 1.0
                matchup_available = False
        elif stat_type == "reb":
            opp_avg_reb = opp.get("avgRebounds")
            league_avg_reb = league_stats.get("reb", 43.5)
            if opp_avg_reb and opp_avg_reb > 0:
                matchup_mult = league_avg_reb / opp_avg_reb
                matchup_mult = max(0.88, min(1.15, matchup_mult))
                matchup_available = True
            else:
                matchup_mult = 1.0
                matchup_available = False
        elif stat_type == "ast":
            opp_avg_steals = opp.get("avgSteals")
            league_avg_steals = league_stats.get("steals", 7.5)
            if opp_avg_steals and opp_avg_steals > 0:
                matchup_mult = league_avg_steals / opp_avg_steals
                matchup_mult = max(0.90, min(1.12, matchup_mult))
                matchup_available = True
            else:
                matchup_mult = 1.0
                matchup_available = False
        elif stat_type == "g":
            if opponent_def_rating and league_avg_def:
                matchup_mult = opponent_def_rating / league_avg_def
                matchup_mult = max(0.85, min(1.20, matchup_mult))
                matchup_available = True
            else:
                matchup_mult = 1.0
                matchup_available = False
        elif stat_type == "sog":
            opp_shots_allowed = opp.get("avgShotsAllowed")
            league_avg_sa = league_stats.get("shots_allowed", 30.0)
            if opp_shots_allowed and opp_shots_allowed > 0:
                matchup_mult = opp_shots_allowed / league_avg_sa
                matchup_mult = max(0.88, min(1.15, matchup_mult))
                matchup_available = True
            else:
                matchup_mult = 1.0
                matchup_available = False
        else:
            matchup_mult = 1.0
            matchup_available = False

    # ── 3. Pace Factor ──
    if game_total and game_total > 0:
        pace_factor = game_total / league_total
        pace_factor = max(0.90, min(1.15, pace_factor))
    else:
        pace_factor = 1.0

    # ── 4. Rest Factor (gradient) ──
    rest_factor = _compute_rest_factor(is_b2b, days_rest, sport=sport)

    # ── 5. Home/Away Adjustment (sport-specific) ──
    _home_away_map = {
        "nba": (1.015, 0.985),
        "nhl": (1.025, 0.975),
        "cbb": (1.04, 0.96),
        "mlb": (1.01, 0.99),
    }
    home_mult, away_mult = _home_away_map.get(sport, (1.03, 0.98))
    home_away_adj = home_mult if is_home else away_mult

    # ── 6. Blowout Discount (points/goals — continuous ramp, not cliff) ──
    # MLB pitcher props: disabled (pitcher gets pulled after fixed IP regardless of score)
    if sport == "mlb":
        blowout_disc = 1.0
    elif stat_type in ("pts", "g") and spread is not None:
        if sport == "nhl" and stat_type == "g":
            # NHL spreads are tighter: 1.5 = big favorite
            blowout_disc = max(0.90, 1.0 - max(0, abs(spread) - 1.5) * 0.04)
        else:
            # NBA/CBB: spread 6=1.0, 7=0.98, 10=0.92, 13.5+=0.85 floor
            blowout_disc = max(0.85, 1.0 - max(0, abs(spread) - 6) * 0.02)
    else:
        blowout_disc = 1.0

    # ── 7. Injury Usage Boost (points only, weighted by player rank) ──
    usage_boost = 0.0
    if stat_type == "pts" and injured_teammates:
        total_lost_ppg = sum(t.get("ppg", 0) for t in injured_teammates)
        # 40% redistribution (bench absorbs the rest) — was 60%
        redistributed = total_lost_ppg * 0.40
        # Rank weights: 45/30/25 (slightly less top-heavy)
        rank_weights = [0.45, 0.30, 0.25]
        rank_idx = min(player_rank, len(rank_weights) - 1)
        usage_boost = redistributed * rank_weights[rank_idx]

    projection = (weighted_avg * matchup_mult * pace_factor *
                  rest_factor * home_away_adj * blowout_disc) + usage_boost
    projection = round(projection, 1)

    # ── Edge calculation ──
    line = posted_line
    line_source = "odds_api" if posted_line is not None else "estimated"
    if line is None:
        line = estimate_line_from_average(season_avg, stat_type)
    if line is None or line <= 0:
        return None

    edge = round(projection - line, 1)

    # ── Slot integration ──
    signal = _apply_slot_integration(edge, slot_type)

    # Cap estimated lines at LEAN max (no STRONG signals on estimated lines)
    if line_source == "estimated" and signal.startswith("STRONG"):
        signal = signal.replace("STRONG", "LEAN")

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
        "line_source": line_source,
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


def estimate_line_from_average(season_avg, stat_type="pts"):
    """
    Tier 2 fallback when no Odds API key: estimated line from season average.
    Books typically set lines slightly below the average.
    Lower-volume stats (reb, ast) get more cushion since variance is higher.
    """
    if season_avg is None or season_avg <= 0:
        return None
    discount = {
        "pts": 0.97, "reb": 0.94, "ast": 0.93, "g": 0.95, "sog": 0.97,
        "k": 0.95, "h": 0.94, "tb": 0.95, "hr": 0.90, "rbi": 0.93, "er": 1.05, "ha": 1.05,
    }.get(stat_type, 0.97)
    return round(season_avg * discount, 1)


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
    return {
        "pts": "pts", "reb": "reb", "ast": "ast", "g": "g", "sog": "sog",
        "k": "k", "h": "h", "tb": "tb", "hr": "hr", "rbi": "rbi", "er": "er", "ha": "ha",
    }.get(stat_type, stat_type)


def get_league_defensive_average(sport="nba"):
    """Simple lookup for league average points allowed."""
    return LEAGUE_AVG_DEF.get(sport, 112.0)
