"""
Calibration Analysis Module — measures and corrects the cover_pct linear formula.

The model outputs cover_pct = 50 + (score / max_score) * 45, a linear mapping
that claims to represent cover probability. This module:
  1. Computes calibration metrics (Brier score, ECE) against historical outcomes
  2. Fits a logistic mapping to learn the true score→probability curve
  3. Falls back to isotonic regression when logistic fit fails
  4. Provides corrected cover_pct values for live predictions
"""

import math
import numpy as np
from constants import get_max_score

# In-memory cache: sport -> {"type": "logistic"|"isotonic", "params": ...}
_calibration_cache = {}

# Bin edges for calibration analysis (8 bins from 50% to 90%+)
_BIN_EDGES = [50, 55, 60, 65, 70, 75, 80, 85, 100]
_BIN_LABELS = [
    "50-55%", "55-60%", "60-65%", "65-70%",
    "70-75%", "75-80%", "80-85%", "85%+",
]

MIN_ISOTONIC_SAMPLES = 30
MIN_LOGISTIC_SAMPLES = 50
ECE_THRESHOLD = 5.0  # Calibration needed when ECE exceeds this


def compute_raw_cover_pct(score, sport):
    """Replicate the linear formula used in game_scanner."""
    max_score = get_max_score(sport)
    return round(50 + (score / max_score) * 45, 1)


def compute_calibration(predictions, sport):
    """
    Full calibration analysis from backtest results.

    Args:
        predictions: list of dicts with "score" (int/float) and "correct" (bool/int)
        sport: sport string for max_score lookup

    Returns:
        dict with brier_score, ece, bins, logistic_params, isotonic_breakpoints,
        adjustment_needed, calibrated_brier_score
    """
    if not predictions:
        return {
            "brier_score": None,
            "calibrated_brier_score": None,
            "ece": None,
            "calibrated_ece": None,
            "bins": [],
            "logistic_params": None,
            "isotonic_breakpoints": None,
            "adjustment_needed": False,
            "sample_size": 0,
        }

    scores = np.array([p["score"] for p in predictions], dtype=float)
    actuals = np.array([1 if p["correct"] else 0 for p in predictions], dtype=float)
    raw_pcts = np.array([compute_raw_cover_pct(s, sport) for s in scores], dtype=float)

    # Brier score: mean((predicted_prob - actual)^2)
    predicted_probs = raw_pcts / 100.0
    brier = float(np.mean((predicted_probs - actuals) ** 2))

    # Binned calibration + ECE
    bins, ece = _compute_binned_ece(raw_pcts, actuals)

    adjustment_needed = ece > ECE_THRESHOLD

    # Fit logistic on score→actual (not raw_pct→actual, to avoid double-mapping)
    logistic_params = _fit_logistic(scores, actuals, sport)

    # Fit isotonic as fallback
    iso_data = _fit_isotonic(raw_pcts, actuals)

    # Compute calibrated Brier/ECE if we have a model
    calibrated_brier = None
    calibrated_ece = None
    if logistic_params:
        cal_pcts = np.array([
            _apply_logistic(s, logistic_params) for s in scores
        ])
        cal_probs = cal_pcts / 100.0
        calibrated_brier = float(np.mean((cal_probs - actuals) ** 2))
        _, calibrated_ece = _compute_binned_ece(cal_pcts, actuals)
    elif iso_data:
        cal_pcts = np.interp(raw_pcts, iso_data["x"], iso_data["y"])
        cal_probs = cal_pcts / 100.0
        calibrated_brier = float(np.mean((cal_probs - actuals) ** 2))
        _, calibrated_ece = _compute_binned_ece(cal_pcts, actuals)

    return {
        "brier_score": round(brier, 4),
        "calibrated_brier_score": round(calibrated_brier, 4) if calibrated_brier is not None else None,
        "ece": ece,
        "calibrated_ece": calibrated_ece,
        "bins": bins,
        "logistic_params": logistic_params,
        "isotonic_breakpoints": iso_data,
        "adjustment_needed": adjustment_needed,
        "sample_size": len(predictions),
    }


def _compute_binned_ece(pcts, actuals):
    """Compute binned calibration and ECE."""
    bins = []
    ece_sum = 0.0
    total_n = len(pcts)

    for i in range(len(_BIN_EDGES) - 1):
        lo, hi = _BIN_EDGES[i], _BIN_EDGES[i + 1]
        if i == len(_BIN_EDGES) - 2:
            mask = (pcts >= lo) & (pcts <= hi)
        else:
            mask = (pcts >= lo) & (pcts < hi)

        count = int(np.sum(mask))
        if count > 0:
            avg_pred = float(np.mean(pcts[mask]))
            actual_rate = float(np.mean(actuals[mask]) * 100)
            gap = round(avg_pred - actual_rate, 2)
        else:
            avg_pred = 0.0
            actual_rate = 0.0
            gap = 0.0

        bins.append({
            "range": _BIN_LABELS[i],
            "count": count,
            "avg_predicted": round(avg_pred, 2),
            "actual_rate": round(actual_rate, 2),
            "gap": gap,
        })

        if count > 0:
            ece_sum += (count / total_n) * abs(avg_pred - actual_rate)

    return bins, round(ece_sum, 2)


# ─── Logistic Fit ──────────────────────────────────────────────────────────────

def _logistic_fn(score, base, amplitude, k, midpoint):
    """Logistic curve: base + amplitude / (1 + exp(-k * (score - midpoint)))."""
    z = -k * (score - midpoint)
    z = np.clip(z, -500, 500)
    return base + amplitude / (1.0 + np.exp(z))


def _fit_logistic(scores, actuals, sport):
    """
    Fit logistic curve: score → cover_probability.

    Uses score directly (not raw_pct) to avoid double-mapping.
    Returns dict with {base, amplitude, k, midpoint, max_score} or None.
    """
    if len(scores) < MIN_LOGISTIC_SAMPLES:
        return None

    try:
        from scipy.optimize import curve_fit
    except ImportError:
        return None

    max_score = get_max_score(sport)
    base_rate = float(np.mean(actuals))

    # Initial parameter guess:
    # base = base_rate (what you'd expect at score=0)
    # amplitude = (0.95 - base_rate) so the curve tops out near 95%
    # k = 0.1 (gentle slope)
    # midpoint = max_score / 2
    p0 = [base_rate, 0.95 - base_rate, 0.1, max_score / 2]

    # Bounds to keep params physically meaningful
    bounds = (
        [0.30, 0.01, 0.001, 0],           # lower bounds
        [0.80, 0.50, 2.0, max_score],      # upper bounds
    )

    try:
        popt, _ = curve_fit(
            _logistic_fn, scores, actuals,
            p0=p0, bounds=bounds, maxfev=5000,
        )
        base, amplitude, k, midpoint = popt

        return {
            "base": round(float(base), 4),
            "amplitude": round(float(amplitude), 4),
            "k": round(float(k), 4),
            "midpoint": round(float(midpoint), 2),
            "max_score": max_score,
        }
    except (RuntimeError, ValueError):
        return None


def _apply_logistic(score, params):
    """Apply fitted logistic model to a single score. Returns cover_pct (0-100)."""
    result = _logistic_fn(
        float(score),
        params["base"],
        params["amplitude"],
        params["k"],
        params["midpoint"],
    )
    return round(float(result) * 100, 1)


# ─── Isotonic Fit (fallback) ──────────────────────────────────────────────────

def _fit_isotonic(raw_pcts, actuals):
    """
    Fit isotonic regression: raw_pct -> actual_cover_rate.

    Returns dict with "x" and "y" arrays (breakpoints), or None if insufficient data.
    """
    if len(raw_pcts) < MIN_ISOTONIC_SAMPLES:
        return None

    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        return None

    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(raw_pcts, actuals)

    # Extract breakpoints from fitted model
    if hasattr(iso, "X_thresholds_") and hasattr(iso, "y_thresholds_"):
        x_bp = iso.X_thresholds_.tolist()
        y_bp = (iso.y_thresholds_ * 100).tolist()
    else:
        x_lin = np.linspace(float(raw_pcts.min()), float(raw_pcts.max()), 50)
        y_lin = iso.predict(x_lin) * 100
        x_bp = x_lin.tolist()
        y_bp = y_lin.tolist()

    x_bp = [round(v, 2) for v in x_bp]
    y_bp = [round(v, 2) for v in y_bp]

    return {"x": x_bp, "y": y_bp}


# ─── Cache Management ─────────────────────────────────────────────────────────

def load_calibration(sport, calibration_data):
    """
    Load calibration model into the in-memory cache for a sport.

    Prefers logistic_params (smoother, no extreme overfitting at sparse bins).
    Falls back to isotonic_breakpoints only if sample size >= 200 (isotonic
    overfits badly on small datasets).
    """
    if calibration_data is None:
        return

    sample_size = calibration_data.get("sample_size", 0)

    # Check if this is the full calibration dict or a sub-dict
    logistic = calibration_data.get("logistic_params")
    iso = calibration_data.get("isotonic_breakpoints")

    # If it's just breakpoints (legacy format), treat as isotonic
    if not logistic and not iso and "x" in calibration_data and "y" in calibration_data:
        iso = calibration_data

    if logistic:
        _calibration_cache[sport] = {
            "type": "logistic",
            "params": logistic,
        }
    elif iso and isinstance(iso, dict) and "x" in iso and "y" in iso and sample_size >= 200:
        _calibration_cache[sport] = {
            "type": "isotonic",
            "params": {"x": iso["x"], "y": iso["y"]},
        }


def get_calibrated_cover_pct(score, sport):
    """
    Apply cached calibration model to get calibrated cover percentage.

    Returns calibrated pct (float) or None if no model loaded.
    """
    if sport not in _calibration_cache:
        return None

    entry = _calibration_cache[sport]

    if entry["type"] == "logistic":
        return _apply_logistic(score, entry["params"])
    elif entry["type"] == "isotonic":
        raw_pct = compute_raw_cover_pct(score, sport)
        bp = entry["params"]
        calibrated = np.interp(raw_pct, bp["x"], bp["y"])
        return round(float(calibrated), 1)

    return None


def is_loaded(sport):
    """Check if calibration model is loaded for a sport."""
    return sport in _calibration_cache


def get_calibration_type(sport):
    """Return the type of calibration loaded ('logistic', 'isotonic', or None)."""
    if sport not in _calibration_cache:
        return None
    return _calibration_cache[sport]["type"]
