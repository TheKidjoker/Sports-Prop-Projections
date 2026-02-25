"""
Calibration Analysis Module — measures and corrects the cover_pct linear formula.

The model outputs cover_pct = 50 + (score / max_score) * 45, a linear mapping
that claims to represent cover probability. This module:
  1. Computes calibration metrics (Brier score, ECE) against historical outcomes
  2. Fits isotonic regression to learn the true score→probability mapping
  3. Provides corrected cover_pct values for live predictions
"""

import numpy as np
from constants import get_max_score

# In-memory cache: sport -> {"x": [...], "y": [...]} isotonic breakpoints
_calibration_cache = {}

# Bin edges for calibration analysis (8 bins from 50% to 90%+)
_BIN_EDGES = [50, 55, 60, 65, 70, 75, 80, 85, 100]
_BIN_LABELS = [
    "50-55%", "55-60%", "60-65%", "65-70%",
    "70-75%", "75-80%", "80-85%", "85%+",
]

MIN_ISOTONIC_SAMPLES = 30


def compute_raw_cover_pct(score, sport):
    """Replicate the linear formula used in game_scanner."""
    max_score = get_max_score(sport)
    return round(50 + (score / max_score) * 45, 1)


def compute_calibration(predictions, sport):
    """
    Full calibration analysis from backtest results.

    Args:
        predictions: list of dicts with "score" (int) and "correct" (bool/int)
        sport: sport string for max_score lookup

    Returns:
        dict with brier_score, ece, bins, isotonic_breakpoints, adjustment_needed
    """
    if not predictions:
        return {
            "brier_score": None,
            "ece": None,
            "bins": [],
            "isotonic_breakpoints": None,
            "adjustment_needed": False,
            "sample_size": 0,
        }

    raw_pcts = []
    actuals = []
    for p in predictions:
        pct = compute_raw_cover_pct(p["score"], sport)
        raw_pcts.append(pct)
        actuals.append(1 if p["correct"] else 0)

    raw_pcts = np.array(raw_pcts, dtype=float)
    actuals = np.array(actuals, dtype=float)

    # Brier score: mean((predicted_prob - actual)^2)
    predicted_probs = raw_pcts / 100.0
    brier = float(np.mean((predicted_probs - actuals) ** 2))

    # Binned calibration + ECE
    bins = []
    ece_sum = 0.0
    total_n = len(raw_pcts)

    for i in range(len(_BIN_EDGES) - 1):
        lo, hi = _BIN_EDGES[i], _BIN_EDGES[i + 1]
        if i == len(_BIN_EDGES) - 2:
            mask = (raw_pcts >= lo) & (raw_pcts <= hi)
        else:
            mask = (raw_pcts >= lo) & (raw_pcts < hi)

        count = int(np.sum(mask))
        if count > 0:
            avg_pred = float(np.mean(raw_pcts[mask]))
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

    ece = round(ece_sum, 2)

    # Isotonic regression
    iso_data = _fit_isotonic(raw_pcts, actuals)

    return {
        "brier_score": round(brier, 4),
        "ece": ece,
        "bins": bins,
        "isotonic_breakpoints": iso_data,
        "adjustment_needed": ece > 10.0,
        "sample_size": len(predictions),
    }


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
        # Fallback: reconstruct via predict on a linspace
        x_lin = np.linspace(float(raw_pcts.min()), float(raw_pcts.max()), 50)
        y_lin = iso.predict(x_lin) * 100
        x_bp = x_lin.tolist()
        y_bp = y_lin.tolist()

    # Round for clean JSON
    x_bp = [round(v, 2) for v in x_bp]
    y_bp = [round(v, 2) for v in y_bp]

    return {"x": x_bp, "y": y_bp}


def load_calibration(sport, calibration_data):
    """
    Load isotonic breakpoints into the in-memory cache for a sport.

    Args:
        sport: sport string
        calibration_data: dict from compute_calibration() result,
                         or just the isotonic_breakpoints sub-dict
    """
    if calibration_data is None:
        return

    # Accept either the full calibration dict or just the breakpoints
    iso = calibration_data
    if "isotonic_breakpoints" in calibration_data:
        iso = calibration_data["isotonic_breakpoints"]

    if iso and isinstance(iso, dict) and "x" in iso and "y" in iso:
        _calibration_cache[sport] = {
            "x": iso["x"],
            "y": iso["y"],
        }


def get_calibrated_cover_pct(score, sport):
    """
    Apply cached isotonic model to get calibrated cover percentage.

    Returns calibrated pct (float) or None if no model loaded.
    """
    if sport not in _calibration_cache:
        return None

    raw_pct = compute_raw_cover_pct(score, sport)
    bp = _calibration_cache[sport]

    calibrated = np.interp(raw_pct, bp["x"], bp["y"])
    return round(float(calibrated), 1)


def is_loaded(sport):
    """Check if calibration model is loaded for a sport."""
    return sport in _calibration_cache
