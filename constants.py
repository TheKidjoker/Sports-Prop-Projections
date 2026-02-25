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


# ─── Proportion Z-Test ─────────────────────────────────────────────────────────

def proportion_z_test(successes, total, baseline=0.50):
    """
    Two-sided z-test for a proportion vs a baseline rate.
    Returns (z_stat, p_value).
    """
    if total == 0:
        return (0.0, 1.0)
    p_hat = successes / total
    se = math.sqrt(baseline * (1 - baseline) / total)
    if se == 0:
        return (0.0, 1.0)
    z = (p_hat - baseline) / se
    # Two-sided p-value using normal CDF approximation
    p_value = 2 * (1 - _normal_cdf(abs(z)))
    return (round(z, 4), round(p_value, 6))


def _normal_cdf(x):
    """Standard normal CDF approximation (Abramowitz & Stegun)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ─── Universal Defaults (Pre-Tuning Baselines) ─────────────────────────────────

UNIVERSAL_DEFAULTS = {
    "lean": "slot_dependent",
    "lean_public": "favorite",
    "lean_vegas": "underdog",
    "public_slot_bonus": 10,
    "b2b_bonus": 4,
    "b2b_penalty": -3,
    "ats_bonus": 4,
    "ats_penalty": -3,
    "home_away_split": 3,
    "h2h_revenge": 3,
    "h2h_dominance": 2,
    "line_toward_dog": 0,
    "line_toward_fav": 0,
    "day_penalties": {},
    "spread_buckets": {},
}


# ─── Override Evidence Thresholds ───────────────────────────────────────────────

OVERRIDE_EVIDENCE_THRESHOLDS = {
    "day_penalty":    {"min_games": 40, "p_threshold": 0.05},
    "spread_bucket":  {"min_games": 50, "p_threshold": 0.05},
    "factor_weight":  {"min_games": 100, "p_threshold": 0.10},
    "lean_direction": {"min_games": 200, "p_threshold": 0.05},
}


# ─── Sport-Specific Override Registry ───────────────────────────────────────────
# Every sport-specific override with metadata: value, sample size, p-value,
# and confidence tier (validated / weak / insufficient_data).

SPORT_OVERRIDES = {
    "nba": {
        "lean_direction":       {"value": "always_underdog", "n": 607, "p_value": 0.001, "confidence": "validated"},
        "tuesday_penalty":      {"value": -3, "n": 87,  "p_value": 0.04, "confidence": "validated"},
        "public_slot_bonus":    {"value": 5,  "n": 607, "p_value": 0.03, "confidence": "validated"},
        "b2b_bonus":            {"value": 2,  "n": 143, "p_value": 0.11, "confidence": "weak"},
        "b2b_penalty":          {"value": -1, "n": 143, "p_value": 0.11, "confidence": "weak"},
        "h2h_revenge":          {"value": 1,  "n": 607, "p_value": 0.22, "confidence": "weak"},
        "h2h_dominance":        {"value": 2,  "n": 607, "p_value": 0.15, "confidence": "weak"},
        "spread_3_5_bonus":     {"value": 2,  "n": 85,  "p_value": 0.09, "confidence": "weak"},
        "spread_5_7_penalty":   {"value": -3, "n": 72,  "p_value": 0.06, "confidence": "weak"},
        "spread_13_plus_penalty": {"value": -3, "n": 45, "p_value": 0.12, "confidence": "weak"},
        "line_toward_dog":      {"value": 3,  "n": 607, "p_value": 0.02, "confidence": "validated"},
        "line_toward_fav":      {"value": -2, "n": 607, "p_value": 0.04, "confidence": "validated"},
        "home_away_split":      {"value": 3,  "n": 607, "p_value": 0.15, "confidence": "weak"},
    },
    "nhl": {
        "lean_direction":       {"value": "always_underdog", "n": 529, "p_value": 0.001, "confidence": "validated"},
        "friday_penalty":       {"value": -3, "n": 73,  "p_value": 0.04, "confidence": "validated"},
        "public_slot_bonus":    {"value": 3,  "n": 529, "p_value": 0.03, "confidence": "validated"},
        "b2b_bonus":            {"value": 0,  "n": 529, "p_value": 0.35, "confidence": "weak"},
        "b2b_penalty":          {"value": -1, "n": 529, "p_value": 0.18, "confidence": "weak"},
        "ats_penalty":          {"value": 0,  "n": 529, "p_value": 0.42, "confidence": "weak"},
        "h2h_revenge":          {"value": 0,  "n": 529, "p_value": 0.55, "confidence": "weak"},
        "h2h_dominance":        {"value": 2,  "n": 529, "p_value": 0.20, "confidence": "weak"},
    },
    "cbb": {
        "public_slot_bonus":    {"value": 3,  "n": 1977, "p_value": 0.02, "confidence": "validated"},
        "sunday_penalty":       {"value": -4, "n": 185,  "p_value": 0.003, "confidence": "validated"},
        "ats_bonus":            {"value": 0,  "n": 1977, "p_value": 0.30, "confidence": "weak"},
        "ats_penalty":          {"value": 2,  "n": 1977, "p_value": 0.04, "confidence": "validated"},
        "home_away_split":      {"value": 0,  "n": 1977, "p_value": 0.01, "confidence": "validated"},
        "h2h_revenge":          {"value": 0,  "n": 1977, "p_value": 0.35, "confidence": "weak"},
        "h2h_dominance":        {"value": 0,  "n": 1977, "p_value": 0.28, "confidence": "weak"},
        "spread_6_10_bonus":    {"value": 3,  "n": 420,  "p_value": 0.001, "confidence": "validated"},
        "spread_0_3_penalty":   {"value": -3, "n": 310,  "p_value": 0.002, "confidence": "validated"},
        "spread_15_plus_penalty": {"value": -2, "n": 150, "p_value": 0.08, "confidence": "weak"},
    },
    "nfl": {
        "lean_direction":       {"value": "flipped", "n": 105, "p_value": 0.08, "confidence": "insufficient_data"},
        "public_slot_bonus":    {"value": 10, "n": 105, "p_value": 0.15, "confidence": "insufficient_data"},
        "home_away_split":      {"value": 0,  "n": 105, "p_value": 0.03, "confidence": "insufficient_data"},
        "h2h_revenge":          {"value": 0,  "n": 105, "p_value": 0.01, "confidence": "insufficient_data"},
        "h2h_dominance":        {"value": 0,  "n": 105, "p_value": 0.02, "confidence": "insufficient_data"},
        "spread_3_7_bonus":     {"value": 3,  "n": 46,  "p_value": 0.06, "confidence": "insufficient_data"},
        "spread_0_3_penalty":   {"value": -3, "n": 21,  "p_value": 0.12, "confidence": "insufficient_data"},
        "spread_10_plus_penalty": {"value": -3, "n": 18, "p_value": 0.09, "confidence": "insufficient_data"},
        "line_toward_dog":      {"value": 3,  "n": 105, "p_value": 0.10, "confidence": "insufficient_data"},
        "line_toward_fav":      {"value": -2, "n": 105, "p_value": 0.12, "confidence": "insufficient_data"},
    },
    "cfb": {},
}


def get_override(sport, override_name, default):
    """Return override value only if confidence is 'validated', else return default."""
    overrides = SPORT_OVERRIDES.get(sport, {})
    entry = overrides.get(override_name)
    if entry and entry.get("confidence") == "validated":
        return entry["value"]
    return default
