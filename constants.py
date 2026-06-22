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
        "vegas": {"strong": 7, "lean": 3},
        "public": {"lean": 5},
        "max_score": 25,
    },
    "cbb": {
        "strong": 13,
        "lean": 10,
        "ml": 7,
        "max_score": 38,
    },
    "cfb": {
        "strong": 11,
        "lean": 9,
        "ml": 7,
        "max_score": 35,
    },
    "nfl": {
        "strong": 15,
        "lean": 8,
        "max_score": 35,
    },
    "mlb": {
        "strong": 7,
        "lean": 4,
        "max_score": 25,
    },
    "soccer": {
        "strong": 8,
        "lean": 5,
        "max_score": 25,
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

DATA_CONFIDENCE_LEVELS = {
    "cbb": {"level": "high",     "games": 1977, "label": "High",     "reason": "Sufficient for most factor validation"},
    "nba": {"level": "medium",   "games": 607,  "label": "Medium",   "reason": "Adequate for core factors, marginal for sub-splits"},
    "nhl": {"level": "medium",   "games": 529,  "label": "Medium",   "reason": "Adequate for core factors"},
    "nfl": {"level": "low",      "games": 105,  "label": "Low",      "reason": "Insufficient for reliable weight tuning"},
    "cfb": {"level": "very_low", "games": 51,   "label": "Very Low", "reason": "All weights essentially unvalidated"},
    "mlb": {"level": "very_low", "games": 0,    "label": "Very Low", "reason": "New sport — collecting historical data"},
}

SPORT_VALIDATION_STATUS = {
    "nhl": {"badge": "EXPERIMENTAL", "css_class": "badge-experimental", "text": "EXPERIMENTAL \u2014 Spread Model"},
    "nba": {"badge": "EXPERIMENTAL", "css_class": "badge-experimental", "text": "EXPERIMENTAL \u2014 Spread Model"},
    "cbb": {"badge": "EXPERIMENTAL", "css_class": "badge-experimental", "text": "EXPERIMENTAL \u2014 Spread Model"},
    "nfl": {"badge": "EXPERIMENTAL", "css_class": "badge-experimental", "text": "EXPERIMENTAL \u2014 Spread Model"},
    "cfb": {"badge": "EXPERIMENTAL", "css_class": "badge-experimental", "text": "EXPERIMENTAL \u2014 Spread Model"},
    "mlb": {"badge": "EXPERIMENTAL", "css_class": "badge-experimental", "text": "EXPERIMENTAL \u2014 Moneyline Model"},
}

PRISM_VALIDATION_STATUS = {
    "badge": "VALIDATED", "css_class": "badge-validated", "text": "VALIDATED \u2014 Player Props (PRISM)"
}

# ─── Validation Tier Configuration ─────────────────────────────────────────
# Dynamic tiers based on best OOS accuracy across rules + EV models.
VALIDATION_TIERS = {
    "validated": {"min_oos": 55.0, "css_class": "badge-validated", "label": "VALIDATED"},
    "caution":   {"min_oos": 52.4, "css_class": "badge-caution",   "label": "CAUTION"},
    "degraded":  {"min_oos": 0.0,  "css_class": "badge-experimental", "label": "DEGRADED"},
}
BREAKEVEN_RATE = 52.38  # -110 standard vig breakeven


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
    "public_slot_bonus": 3,      # was 10; aligned with NHL/CBB validated values
    "b2b_bonus": 2,              # was 4; NHL -3.9% lift, NBA tuned to 2
    "b2b_penalty": -1,           # was -3; NHL/NBA both tuned to -1
    "ats_bonus": 2,              # was 4; CBB validated at 0, reduced
    "ats_penalty": 0,            # was -3; too harsh, NHL validated at 0
    "home_away_split": 0,        # was 3; marginal ~0% everywhere, harmful
    "h2h_revenge": 0,            # was 3; noise/harmful in all sports
    "h2h_dominance": 0,          # was 2; negative standalone everywhere
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
        "b2b_bonus":            {"value": 4,  "n": 143, "p_value": 0.11, "confidence": "validated"},
        "b2b_penalty":          {"value": -3, "n": 143, "p_value": 0.11, "confidence": "validated"},
        "ats_bonus":            {"value": 4,  "n": 607, "p_value": 0.10, "confidence": "validated"},
        "ats_penalty":          {"value": -3, "n": 607, "p_value": 0.10, "confidence": "validated"},
        "h2h_revenge":          {"value": 3,  "n": 607, "p_value": 0.22, "confidence": "validated"},
        "h2h_dominance":        {"value": 2,  "n": 607, "p_value": 0.15, "confidence": "validated"},
        "spread_3_5_bonus":     {"value": 2,  "n": 85,  "p_value": 0.09, "confidence": "weak"},
        "spread_5_7_penalty":   {"value": -3, "n": 72,  "p_value": 0.06, "confidence": "weak"},
        "spread_13_plus_penalty": {"value": -3, "n": 45, "p_value": 0.12, "confidence": "weak"},
        "line_toward_dog":      {"value": 3,  "n": 607, "p_value": 0.02, "confidence": "validated"},
        "line_toward_fav":      {"value": -2, "n": 607, "p_value": 0.04, "confidence": "validated"},
        "home_away_split":      {"value": 3,  "n": 607, "p_value": 0.15, "confidence": "validated"},
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
    "mlb": {},
}


def get_override(sport, override_name, default):
    """Return override value only if confidence is 'validated', else return default."""
    overrides = SPORT_OVERRIDES.get(sport, {})
    entry = overrides.get(override_name)
    if entry and entry.get("confidence") == "validated":
        return entry["value"]
    return default


# ─── NBA EV Model Configuration ──────────────────────────────────────────────

# ─── NBA Unvalidated Factor Caps ─────────────────────────────────────────
# Walk-forward validation showed NBA rules model at 49% OOS (coin flip).
# Cap unvalidated factors to reduce noise until Phase 3 isolation testing.
NBA_UNVALIDATED_CAPS = {
    "vegas_trap": 7,       # reverted to pre-V6 uncapped
    "trell": 5,            # reverted to pre-V6 uncapped
    "public_betting": 5,   # reverted to pre-V6 uncapped
    "feedback": 0,         # zero permanently (circular dependency)
}

CBB_UNVALIDATED_CAPS = {
    "vegas_trap": 2,
    "trell": 3,
    "public_betting": 1,
    "feedback": 0,
}

UNVALIDATED_SPORTS = {"cbb", "mlb"}


# ─── Signal Decay Classification ──────────────────────────────────────────
# How quickly each factor's signal degrades after the scan was produced.
# "fast" = line already moved, "slow" = changes over hours, "none" = schedule fact.

# ─── Feature Flags (Rollback Safety) ─────────────────────────────────────────
# Each algorithm upgrade can be disabled independently.
USE_DYNAMIC_PRISM_WEIGHTS = True
USE_ZSCORE_MATCHUP = True
USE_ELO_FEATURES = True
USE_POISSON_VARIANCE = True

# ─── Synthetic Market Maker Constants ─────────────────────────────────────────

POINTS_PER_ELO = {
    "nba": 28.0,
    "nhl": 67.0,
    "nfl": 25.0,
    "cfb": 25.0,
    "cbb": 28.0,
    "mlb": 40.0,
    "soccer": 35.0,
}

SOCCER_LEAGUES = {
    "epl": {"name": "Premier League", "api_id": 39, "country": "England"},
    "la_liga": {"name": "La Liga", "api_id": 140, "country": "Spain"},
    "bundesliga": {"name": "Bundesliga", "api_id": 78, "country": "Germany"},
    "serie_a": {"name": "Serie A", "api_id": 135, "country": "Italy"},
    "ligue_1": {"name": "Ligue 1", "api_id": 61, "country": "France"},
    "mls": {"name": "MLS", "api_id": 253, "country": "USA"},
    "ucl": {"name": "Champions League", "api_id": 2, "country": "Europe"},
    "eredivisie": {"name": "Eredivisie", "api_id": 88, "country": "Netherlands"},
    "liga_portugal": {"name": "Liga Portugal", "api_id": 94, "country": "Portugal"},
    "super_lig": {"name": "Super Lig", "api_id": 203, "country": "Turkey"},
    "championship": {"name": "Championship", "api_id": 40, "country": "England"},
    "liga_mx": {"name": "Liga MX", "api_id": 262, "country": "Mexico"},
    "a_league": {"name": "A-League", "api_id": 188, "country": "Australia"},
    "j_league": {"name": "J1 League", "api_id": 98, "country": "Japan"},
    "k_league": {"name": "K League 1", "api_id": 292, "country": "South Korea"},
    "saudi_pro": {"name": "Saudi Pro League", "api_id": 307, "country": "Saudi Arabia"},
}

STANDARD_OVERROUND = {
    "nba": 0.045,
    "nhl": 0.050,
    "nfl": 0.045,
    "cfb": 0.045,
    "cbb": 0.045,
    "mlb": 0.040,
    "soccer": 0.055,
}


EV_CONFIG = {
    "auc_gate": 0.60,               # Minimum AUC-ROC to activate model (raised for elo_diff)
    "auc_gate_standalone": 0.62,    # Higher gate when EV is the ONLY model (no rules)
    "implied_prob": 110 / (100 + 110),  # 0.5238 at -110 standard vig
    "edge_tiers": {
        "strong": 0.06,             # 6%+ edge → STRONG PLAY (was 8%)
        "confident": 0.04,          # 4-6% edge → CONFIDENT (was 5%)
        "lean": 0.02,               # 2-4% edge → LEAN (was 3%)
    },
    "train_split": 0.70,            # 70/30 chronological split
    "regularization_C": 0.1,        # L2 regularization strength
    "warmup_games": 20,             # Min team games before feature extraction
    "rolling_window": 20,           # Team state rolling window size
    "regressed_prior_weight": 15,   # Bayesian shrinkage prior weight (was 10)
    "league_avg_score": 105.0,      # NBA league average PPG default
    "feature_names": [
        "spread_abs", "clv", "rest_diff",
        "dog_off_regressed", "fav_off_regressed", "net_rating_diff",
        "dog_win_pct_10", "fav_win_pct_10",
        "home_away", "elo_diff", "pace_diff",
        "synthetic_edge", "market_width", "vig_shading_direction",
    ],
}
