# ─── Named Constants ───────────────────────────────────────────────────────────
# Recommendation thresholds, max scores, moneyline thresholds, and statistical
# utilities by sport.
# Single source of truth — used by game_scanner, app.py, rules_backtest, etc.

import math

# Recommendation thresholds by sport and slot type.
# Each sport has: strong, lean, max_score, and optionally confident, lean_public, ml.
THRESHOLDS = {
    "nba": {
        "vegas": {"strong": 10, "confident": 7, "lean": 5},
        "public": {"strong": 10, "lean": 7},
        "max_score": 44,
    },
    "nhl": {
        "vegas": {"strong": 8, "lean": 3},
        "public": {"lean": 5},
        "max_score": 42,
    },
    "cbb": {
        "strong": 13,
        "lean": 10,
        "ml": 7,
        "max_score": 37,
    },
    "cfb": {
        "strong": 15,
        "lean": 12,
        "ml": 10,
        "max_score": 48,
    },
    "nfl": {
        "strong": 20,
        "lean": 10,
        "max_score": 35,
    },
}

# Moneyline spread thresholds — recommend ML when |spread| >= threshold
ML_THRESHOLDS = {
    "nba": 6,
    "nfl": 3,
    "cfb": 7,
    "cbb": 7,
}


def get_max_score(sport):
    """Return max possible score for a sport."""
    return THRESHOLDS.get(sport, THRESHOLDS["nhl"])["max_score"]


def get_recommendation(score, slot_type, sport):
    """
    Determine recommendation label from score, slot type, and sport.

    Returns one of: "STRONG PLAY", "CONFIDENT", "LEAN", "MONITOR"
    """
    cfg = THRESHOLDS.get(sport)
    if cfg is None:
        cfg = THRESHOLDS["cfb"]  # fallback to generic

    # Sports with per-slot thresholds (NBA, NHL)
    if sport == "nba":
        slot_cfg = cfg.get(slot_type, cfg.get("vegas"))
        if score >= slot_cfg.get("strong", 999):
            return "STRONG PLAY"
        if score >= slot_cfg.get("confident", 999):
            return "CONFIDENT"
        if score >= slot_cfg.get("lean", 999):
            return "LEAN"
        return "MONITOR"

    if sport == "nhl":
        if slot_type == "public":
            slot_cfg = cfg["public"]
            if score >= slot_cfg.get("lean", 999):
                return "LEAN"
            return "MONITOR"
        else:
            slot_cfg = cfg["vegas"]
            if score >= slot_cfg.get("strong", 999):
                return "STRONG PLAY"
            if score >= slot_cfg.get("lean", 999):
                return "LEAN"
            return "MONITOR"

    # Sports with flat thresholds (CBB, CFB, NFL)
    if score >= cfg.get("strong", 999):
        return "STRONG PLAY"
    if score >= cfg.get("lean", 999):
        return "LEAN"
    return "MONITOR"


# ─── Confidence Interval Utilities ────────────────────────────────────────────

# Minimum sample sizes before a metric is considered reliable.
MIN_SAMPLES = {
    "tier": 30,        # recommendation tier (STRONG/CONFIDENT/LEAN)
    "factor": 50,      # individual factor fire count
    "day": 40,         # day-of-week breakdown
    "slot": 80,        # slot type (public/vegas)
    "ats": 15,         # team ATS record
    "feedback": 40,    # feedback loop hit rates
    "overall": 30,     # overall accuracy
}


def wilson_interval(wins, total, z=1.96):
    """
    Wilson score interval for binomial proportion (95% CI by default).
    More accurate than normal approximation for small samples.

    Returns (lower, upper) as percentages (0-100 scale).
    """
    if total == 0:
        return (0.0, 0.0)
    p_hat = wins / total
    denominator = 1 + z * z / total
    center = (p_hat + z * z / (2 * total)) / denominator
    margin = (z / denominator) * math.sqrt(
        p_hat * (1 - p_hat) / total + z * z / (4 * total * total)
    )
    lower = max(0, center - margin)
    upper = min(1, center + margin)
    return (round(lower * 100, 2), round(upper * 100, 2))


def metric_with_ci(wins, total, min_sample=None, z=1.96):
    """
    Build a metric dict with point estimate + Wilson CI + sample info.

    Returns dict with:
      value: point estimate percentage
      ci_lower, ci_upper: 95% Wilson CI bounds
      n: sample size
      below_minimum: True if n < min_sample
    """
    if total == 0:
        return {
            "value": 0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "n": 0,
            "below_minimum": True,
        }
    value = round(wins / total * 100, 2)
    ci_lower, ci_upper = wilson_interval(wins, total, z)
    below = (total < min_sample) if min_sample else False
    return {
        "value": value,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "n": total,
        "below_minimum": below,
    }
