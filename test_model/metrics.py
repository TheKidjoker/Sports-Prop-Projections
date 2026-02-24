"""
Test Model Metrics — accuracy, ROI, CLV, calibration, threshold analysis.
"""


def compute_metrics(predictions):
    """
    Compute comprehensive metrics from a list of prediction dicts.

    Each prediction dict should have:
        model_prob, actual, closing_implied_prob, implied_edge, ev, projected_roi

    Returns:
        Dict with accuracy, roi, clv_avg, calibration_error, threshold_analysis,
        confidence_buckets, total_predictions, qualified_bets
    """
    if not predictions:
        return _empty_metrics()

    total = len(predictions)

    # ── Accuracy: directional correctness ──
    correct = 0
    for p in predictions:
        predicted_cover = 1 if p["model_prob"] >= 0.5 else 0
        if predicted_cover == p["actual"]:
            correct += 1
    accuracy = round(correct / total * 100, 2) if total > 0 else 0

    # ── ROI: at -110 vig, betting when model_prob >= 0.55 ──
    qualified = [p for p in predictions if p["model_prob"] >= 0.55]
    qualified_count = len(qualified)

    if qualified_count > 0:
        total_wagered = qualified_count  # 1 unit each
        total_returned = 0
        for p in qualified:
            predicted_side = 1 if p["model_prob"] >= 0.5 else 0
            if predicted_side == p["actual"]:
                total_returned += 1 + (100 / 110)  # Return stake + win at -110
            # Else lose the unit (0 returned)
        roi = round((total_returned - total_wagered) / total_wagered * 100, 2)
    else:
        roi = 0

    # ── CLV (Closing Line Value) ──
    clv_values = [p["implied_edge"] for p in qualified if p.get("implied_edge") is not None]
    clv_avg = round(sum(clv_values) / len(clv_values) * 100, 2) if clv_values else 0

    # ── Calibration Error (ECE) ──
    calibration_error = _compute_ece(predictions)

    # ── Threshold Analysis ──
    thresholds = [0.52, 0.55, 0.58, 0.60, 0.65]
    threshold_analysis = {}
    for t in thresholds:
        t_preds = [p for p in predictions if p["model_prob"] >= t]
        t_count = len(t_preds)
        if t_count > 0:
            t_correct = sum(1 for p in t_preds if (1 if p["model_prob"] >= 0.5 else 0) == p["actual"])
            t_accuracy = round(t_correct / t_count * 100, 2)

            t_wagered = t_count
            t_returned = sum(
                (1 + 100 / 110) if (1 if p["model_prob"] >= 0.5 else 0) == p["actual"] else 0
                for p in t_preds
            )
            t_roi = round((t_returned - t_wagered) / t_wagered * 100, 2)
        else:
            t_accuracy = 0
            t_roi = 0

        threshold_analysis[str(t)] = {
            "threshold": t,
            "bet_count": t_count,
            "accuracy": t_accuracy,
            "roi": t_roi,
        }

    # ── Confidence Buckets ──
    buckets = [
        ("0.50-0.55", 0.50, 0.55),
        ("0.55-0.60", 0.55, 0.60),
        ("0.60-0.65", 0.60, 0.65),
        ("0.65+", 0.65, 1.01),
    ]
    confidence_buckets = {}
    for label, lo, hi in buckets:
        bucket_preds = [p for p in predictions if lo <= p["model_prob"] < hi]
        bucket_count = len(bucket_preds)
        if bucket_count > 0:
            bucket_hits = sum(1 for p in bucket_preds if p["actual"] == 1)
            hit_rate = round(bucket_hits / bucket_count * 100, 2)
        else:
            hit_rate = 0
        confidence_buckets[label] = {
            "count": bucket_count,
            "hit_rate": hit_rate,
        }

    return {
        "accuracy": accuracy,
        "roi": roi,
        "clv_avg": clv_avg,
        "calibration_error": calibration_error,
        "total_predictions": total,
        "qualified_bets": qualified_count,
        "threshold_analysis": threshold_analysis,
        "confidence_buckets": confidence_buckets,
    }


def _compute_ece(predictions, n_bins=10):
    """Expected Calibration Error — binned."""
    if not predictions:
        return 0

    bins = [[] for _ in range(n_bins)]
    for p in predictions:
        prob = p["model_prob"]
        bin_idx = min(int(prob * n_bins), n_bins - 1)
        bins[bin_idx].append(p)

    ece = 0
    total = len(predictions)
    for bin_preds in bins:
        if not bin_preds:
            continue
        avg_prob = sum(p["model_prob"] for p in bin_preds) / len(bin_preds)
        avg_actual = sum(p["actual"] for p in bin_preds) / len(bin_preds)
        ece += len(bin_preds) / total * abs(avg_prob - avg_actual)

    return round(ece, 4)


def _empty_metrics():
    return {
        "accuracy": 0,
        "roi": 0,
        "clv_avg": 0,
        "calibration_error": 0,
        "total_predictions": 0,
        "qualified_bets": 0,
        "threshold_analysis": {},
        "confidence_buckets": {},
    }
