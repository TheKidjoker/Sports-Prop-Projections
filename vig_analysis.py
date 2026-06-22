# ─── Vig Analysis Module ──────────────────────────────────────────────────────
# Vig stripping (proportional & Shin's method), shading detection, market width.

import math
from prop_ev_engine import american_to_implied_prob


def strip_vig(home_odds, away_odds, method="proportional"):
    """
    Remove vig from a two-way market to get fair probabilities.

    Methods:
        "proportional" — Simple normalization: fair_i = implied_i / total
        "shin" — Shin's method: accounts for favorite-longshot bias

    Args:
        home_odds: American odds for home
        away_odds: American odds for away
        method: "proportional" or "shin"

    Returns:
        dict with home_fair, away_fair, overround (percentage)
    """
    imp_home = american_to_implied_prob(home_odds)
    imp_away = american_to_implied_prob(away_odds)

    if imp_home is None or imp_away is None:
        return None

    total = imp_home + imp_away
    overround = (total - 1.0) * 100

    if method == "shin":
        return _shin_strip_2way(imp_home, imp_away, overround)

    # Proportional
    if total <= 0:
        return None

    return {
        "home_fair": round(imp_home / total, 4),
        "away_fair": round(imp_away / total, 4),
        "overround": round(overround, 2),
    }


def _shin_strip_2way(imp_home, imp_away, overround):
    """
    Shin's method for 2-way markets.

    Shin's model accounts for the favorite-longshot bias: bookmakers tend to
    overcharge longshots more than favorites. The parameter z represents the
    proportion of informed traders in the market.

    For a 2-way market, Shin's solution reduces to solving:
    z = 1 - sqrt(1 - 4*(1 - 1/total)*imp_i*(1-imp_i)/total) ... iteratively

    Simplified 2-way Shin: fair_i = (sqrt(z^2 + 4*(1-z)*imp_i^2 / total) - z) / (2*(1-z)/total)
    """
    total = imp_home + imp_away
    if total <= 1.0:
        return {
            "home_fair": round(imp_home, 4),
            "away_fair": round(imp_away, 4),
            "overround": round(overround, 2),
        }

    # Estimate z (Shin's insider proportion) from overround
    # Approximation: z ≈ (total - 1) / (n - 1) where n = number of outcomes
    z = max(0.001, min(0.15, (total - 1.0)))

    def shin_fair(imp_prob):
        """Apply Shin's formula for a single outcome."""
        discriminant = z * z + 4 * (1 - z) * (imp_prob * imp_prob) / total
        if discriminant < 0:
            return imp_prob / total  # Fallback to proportional
        return (math.sqrt(discriminant) - z) / (2 * (1 - z) / total)

    home_fair = shin_fair(imp_home)
    away_fair = shin_fair(imp_away)

    # Renormalize to sum to 1.0
    fair_total = home_fair + away_fair
    if fair_total > 0:
        home_fair /= fair_total
        away_fair /= fair_total

    return {
        "home_fair": round(home_fair, 4),
        "away_fair": round(away_fair, 4),
        "overround": round(overround, 2),
    }


def strip_vig_3way(home_odds, draw_odds, away_odds):
    """
    Remove vig from a 3-way market (soccer 1X2).

    Uses proportional method — Shin's for 3-way is more complex
    and the additional precision isn't worth the implementation cost
    for initial deployment.

    Args:
        home_odds: American odds for home win
        draw_odds: American odds for draw
        away_odds: American odds for away win

    Returns:
        dict with home_fair, draw_fair, away_fair, overround
    """
    imp_home = american_to_implied_prob(home_odds)
    imp_draw = american_to_implied_prob(draw_odds)
    imp_away = american_to_implied_prob(away_odds)

    if any(p is None for p in [imp_home, imp_draw, imp_away]):
        return None

    total = imp_home + imp_draw + imp_away
    if total <= 0:
        return None

    overround = (total - 1.0) * 100

    return {
        "home_fair": round(imp_home / total, 4),
        "draw_fair": round(imp_draw / total, 4),
        "away_fair": round(imp_away / total, 4),
        "overround": round(overround, 2),
    }


def detect_vig_shading(pinnacle_line, consensus_line, threshold=1.0):
    """
    Identify where books shade lines toward public money.
    Pinnacle is the sharpest book — deviation from Pinnacle = shading.

    The fade direction (opposite of shading) is the value play.

    Args:
        pinnacle_line: Pinnacle spread
        consensus_line: Consensus (average) spread
        threshold: minimum difference to flag as shaded (default 1.0 pts)

    Returns:
        dict with is_shaded, shade_direction, fade_direction, difference
    """
    if pinnacle_line is None or consensus_line is None:
        return {"is_shaded": False, "shade_direction": None, "fade_direction": None, "difference": 0.0}

    diff = consensus_line - pinnacle_line

    if abs(diff) < threshold:
        return {
            "is_shaded": False,
            "shade_direction": None,
            "fade_direction": None,
            "difference": round(abs(diff), 1),
        }

    # More negative consensus = shaded toward home (public on home)
    # Value play: fade home, take away
    if diff < 0:
        shade_dir = "home"
        fade_dir = "away"
    else:
        shade_dir = "away"
        fade_dir = "home"

    return {
        "is_shaded": True,
        "shade_direction": shade_dir,
        "fade_direction": fade_dir,
        "difference": round(abs(diff), 1),
    }


def compute_market_width(lines):
    """
    Spread between best and worst line across books.
    Wide market = less efficient = more opportunity for +EV.

    Args:
        lines: list of spread values from different bookmakers

    Returns:
        dict with width, best, worst, count
    """
    if not lines:
        return {"width": 0.0, "best": None, "worst": None, "count": 0}

    valid = [l for l in lines if l is not None]
    if not valid:
        return {"width": 0.0, "best": None, "worst": None, "count": 0}

    # For spreads: "best" = most positive (most points for underdog)
    # "worst" = most negative (fewest points)
    best = max(valid)
    worst = min(valid)
    width = best - worst

    return {
        "width": round(width, 1),
        "best": best,
        "worst": worst,
        "count": len(valid),
    }
