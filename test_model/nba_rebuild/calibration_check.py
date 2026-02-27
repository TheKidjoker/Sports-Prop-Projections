"""
Phase 7: Calibration Validation

After Phase 4 produces new model (or Phase 5 EV model finalizes):
- Bin predictions by predicted cover%
- Compute Brier score and ECE
- If ECE > 5%, fit logistic from walk-forward training data
- Validate parlay tiers: 80% predicted should ~80% actual
"""

import math
import threading

from constants import wilson_interval

# ─── Progress tracking ────────────────────────────────────────────────────

_progress = {}
_lock = threading.Lock()


def get_calibration_status():
    with _lock:
        return dict(_progress)


def start_calibration_thread():
    with _lock:
        if _progress.get("status") == "running":
            return False
        _progress.clear()
        _progress["status"] = "running"

    t = threading.Thread(target=_run_calibration, daemon=True)
    t.start()
    return True


def _run_calibration():
    try:
        result = validate_calibration()
        with _lock:
            _progress["status"] = "complete"
            _progress["result"] = result
    except Exception as e:
        with _lock:
            _progress["status"] = "error"
            _progress["error"] = str(e)


# ─── Core ─────────────────────────────────────────────────────────────────

def validate_calibration():
    """
    Validate calibration of NBA predictions using walk-forward OOS data.

    Sources (checked in order):
    1. EV model rolling validation (if available)
    2. Combined rebuild model (Phase 4 output)
    3. Rules backtest (legacy)

    Returns:
        brier, ece, reliability_diagram, parlay_validation,
        needs_recalibration, logistic_params
    """
    from test_model import db as tm_db

    predictions = None
    source = None

    # Try EV model rolling validation first
    ev_run = tm_db.get_latest_model_run("nba", "ev_logistic")
    if ev_run and ev_run.get("model_params"):
        rolling = ev_run["model_params"].get("rolling_validation")
        if rolling and "error" not in rolling:
            # Reconstruct predictions from edge buckets (approximate)
            predictions = _extract_ev_predictions(ev_run["model_params"])
            source = "ev_logistic"

    # Try combined rebuild
    if predictions is None:
        combined_run = tm_db.get_latest_model_run("nba", "nba_combined_rebuild")
        if combined_run and combined_run.get("model_params"):
            params = combined_run["model_params"]
            if params.get("passes_validation"):
                predictions = _extract_rules_predictions(params)
                source = "nba_combined_rebuild"

    # Try rules backtest
    if predictions is None:
        rules_run = tm_db.get_latest_model_run("nba", "rules_backtest")
        if rules_run and rules_run.get("model_params"):
            predictions = _extract_rules_predictions(rules_run["model_params"])
            source = "rules_backtest"

    if predictions is None or len(predictions) < 50:
        return {
            "error": "Insufficient prediction data for calibration validation.",
            "source": source,
            "n": len(predictions) if predictions else 0,
        }

    with _lock:
        _progress["source"] = source
        _progress["n_predictions"] = len(predictions)

    # Compute Brier score
    brier = _compute_brier(predictions)

    # Compute ECE
    ece, reliability_bins = _compute_ece_detailed(predictions)

    # Parlay tier validation
    parlay_validation = _validate_parlay_tiers(predictions)

    # Determine if recalibration is needed
    needs_recalibration = ece > 5.0

    # Fit logistic if needed
    logistic_params = None
    if needs_recalibration:
        logistic_params = _fit_logistic_calibration(predictions)

    result = {
        "source": source,
        "n_predictions": len(predictions),
        "brier_score": brier,
        "ece": ece,
        "needs_recalibration": needs_recalibration,
        "reliability_diagram": reliability_bins,
        "parlay_validation": parlay_validation,
        "logistic_params": logistic_params,
    }

    # Save results
    try:
        tm_db.save_model_run({
            "sport": "nba",
            "run_type": "nba_calibration_check",
            "accuracy": 100 - ece,  # Higher = better calibrated
            "total_predictions": len(predictions),
            "model_params": result,
        })
    except Exception:
        pass

    return result


def _extract_ev_predictions(model_params):
    """Extract (predicted_prob, actual_outcome) pairs from EV model results."""
    # The EV model stores edge bucket data but not individual predictions.
    # We need to reconstruct from the stored rolling validation data.
    # For now, return the edge buckets as binned predictions.
    edge_buckets = model_params.get("edge_buckets", [])
    if not edge_buckets:
        rolling = model_params.get("rolling_validation", {})
        edge_buckets = rolling.get("edge_buckets", [])

    if not edge_buckets:
        return None

    predictions = []
    implied = 110 / (100 + 110)  # 0.5238

    for bucket in edge_buckets:
        count = bucket.get("count", 0)
        if count == 0:
            continue
        avg_edge = bucket.get("avg_edge", 0) / 100  # Convert from percentage
        predicted_prob = implied + avg_edge
        accuracy = bucket.get("accuracy", 50) / 100
        # Generate synthetic predictions for this bucket
        wins = int(count * accuracy)
        for _ in range(wins):
            predictions.append((predicted_prob, 1))
        for _ in range(count - wins):
            predictions.append((predicted_prob, 0))

    return predictions if len(predictions) >= 50 else None


def _extract_rules_predictions(model_params):
    """Extract predictions from rules model results."""
    # Rules models produce score-based predictions, not probabilities.
    # Use calibration params if available.
    cal = model_params.get("calibration")
    if cal and cal.get("logistic"):
        # Reconstruct from logistic params + tier data
        tiers = model_params.get("tiers", {})
        predictions = []
        for tier_name, tier_data in tiers.items():
            if not isinstance(tier_data, dict):
                continue
            n = tier_data.get("n", 0)
            wins = tier_data.get("wins", 0)
            if n == 0:
                continue
            # Use tier accuracy as predicted prob (approximate)
            predicted = tier_data.get("accuracy", 50) / 100
            for _ in range(wins):
                predictions.append((predicted, 1))
            for _ in range(n - wins):
                predictions.append((predicted, 0))
        return predictions if len(predictions) >= 50 else None

    return None


def _compute_brier(predictions):
    """Brier score: mean squared error of probability predictions."""
    if not predictions:
        return 1.0
    total = sum((pred - actual) ** 2 for pred, actual in predictions)
    return round(total / len(predictions), 4)


def _compute_ece_detailed(predictions, n_bins=10):
    """
    Expected Calibration Error with per-bin reliability diagram data.

    Returns:
        (ece_pct, bins_list)
    """
    if not predictions:
        return 0.0, []

    # Sort into bins
    bins = [[] for _ in range(n_bins)]
    for pred, actual in predictions:
        bin_idx = min(int(pred * n_bins), n_bins - 1)
        bins[bin_idx].append((pred, actual))

    total = len(predictions)
    ece = 0.0
    reliability_bins = []

    for i in range(n_bins):
        if not bins[i]:
            reliability_bins.append({
                "bin": f"{i/n_bins:.1f}-{(i+1)/n_bins:.1f}",
                "count": 0,
                "avg_predicted": 0,
                "avg_actual": 0,
                "gap": 0,
            })
            continue

        avg_pred = sum(p for p, _ in bins[i]) / len(bins[i])
        avg_actual = sum(a for _, a in bins[i]) / len(bins[i])
        gap = abs(avg_pred - avg_actual)
        ece += (len(bins[i]) / total) * gap

        reliability_bins.append({
            "bin": f"{i/n_bins:.1f}-{(i+1)/n_bins:.1f}",
            "count": len(bins[i]),
            "avg_predicted": round(avg_pred * 100, 1),
            "avg_actual": round(avg_actual * 100, 1),
            "gap": round(gap * 100, 1),
        })

    return round(ece * 100, 2), reliability_bins


def _validate_parlay_tiers(predictions):
    """
    Validate parlay tier calibration.

    For predicted probability bins (60%, 70%, 80%), check that
    actual rates are within 3% of predicted.
    """
    tier_checks = [
        ("60%", 0.55, 0.65),
        ("70%", 0.65, 0.75),
        ("80%", 0.75, 0.85),
        ("90%", 0.85, 0.95),
    ]

    results = {}
    for label, lo, hi in tier_checks:
        tier_preds = [(p, a) for p, a in predictions if lo <= p < hi]
        if len(tier_preds) < 10:
            results[label] = {"n": len(tier_preds), "status": "insufficient_data"}
            continue

        avg_predicted = sum(p for p, _ in tier_preds) / len(tier_preds)
        avg_actual = sum(a for _, a in tier_preds) / len(tier_preds)
        gap = abs(avg_predicted - avg_actual)
        calibrated = gap <= 0.03

        ci = wilson_interval(
            sum(1 for _, a in tier_preds if a == 1),
            len(tier_preds)
        )

        results[label] = {
            "n": len(tier_preds),
            "predicted": round(avg_predicted * 100, 1),
            "actual": round(avg_actual * 100, 1),
            "gap": round(gap * 100, 1),
            "calibrated": calibrated,
            "ci_lower": ci[0],
            "ci_upper": ci[1],
        }

    return results


def _fit_logistic_calibration(predictions):
    """Fit logistic calibration curve to predictions."""
    if len(predictions) < 50:
        return None

    try:
        # Convert predicted probabilities to log-odds
        preds = []
        actuals = []
        for p, a in predictions:
            eps = 1e-7
            p_clipped = max(eps, min(1 - eps, p))
            preds.append(math.log(p_clipped / (1 - p_clipped)))
            actuals.append(a)

        # Simple logistic fit using Newton's method (avoid sklearn dependency)
        # z = a * log_odds + b
        # Start at identity: a=1, b=0
        a, b = 1.0, 0.0
        lr = 0.01

        for _ in range(1000):
            grad_a, grad_b = 0.0, 0.0
            for lo, actual in zip(preds, actuals):
                z = a * lo + b
                if z > 20:
                    p_cal = 1.0
                elif z < -20:
                    p_cal = 0.0
                else:
                    p_cal = 1 / (1 + math.exp(-z))
                err = p_cal - actual
                grad_a += err * lo
                grad_b += err

            n = len(preds)
            a -= lr * grad_a / n
            b -= lr * grad_b / n

        return {
            "a": round(a, 6),
            "b": round(b, 6),
            "description": "Calibrated_prob = sigmoid(a * log_odds + b)",
        }
    except Exception:
        return None
