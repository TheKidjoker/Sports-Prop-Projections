# ─── CLV Tracker ─────────────────────────────────────────────────────────────
# Closing Line Value as north-star metric for betting edge validation.
# CLV measures whether you're consistently beating the closing line —
# the most efficient predictor of game outcomes.

import math


def compute_clv(line_at_pick, closing_line, side="dog"):
    """
    Compute CLV from the bettor's perspective.

    Args:
        line_at_pick: spread when the pick was made (e.g., -3.5)
        closing_line: spread at game start (e.g., -4.5)
        side: "dog" or "fav" — which side the bettor took

    Returns:
        float CLV in points (positive = beat the close)
    """
    if line_at_pick is None or closing_line is None:
        return None

    movement = closing_line - line_at_pick

    if side == "dog":
        # Dog bettor benefits when line moves toward fav (more negative)
        # e.g., picked +3.5, closed +4.5 → got extra point → CLV = +1.0
        return round(movement, 2)
    else:
        # Fav bettor benefits when line moves toward dog (less negative)
        # e.g., picked -3.5, closed -2.5 → got better number → CLV = +1.0
        return round(-movement, 2)


def compute_clv_probability(clv_points, sport="nba"):
    """
    Estimate the edge implied by CLV in points.

    A 1-point CLV on a -110 spread roughly equals a 2.8% edge.
    Sport-specific adjustments for scoring environments.

    Args:
        clv_points: CLV in spread points
        sport: sport key for calibration

    Returns:
        float estimated edge percentage
    """
    # Points-per-percentage mapping (how much 1 spread point = % edge)
    SPORT_CLV_FACTOR = {
        "nba": 2.8,
        "nhl": 4.5,     # Lower scoring → each point worth more
        "nfl": 3.0,
        "cfb": 2.5,
        "cbb": 2.8,
        "mlb": 3.5,     # Run line CLV
        "soccer": 5.0,  # Very low scoring → each goal worth a lot
    }

    factor = SPORT_CLV_FACTOR.get(sport, 2.8)
    return round(clv_points * factor, 2)


def rolling_clv_dashboard(predictions, sport=None, window=50):
    """
    Build a CLV dashboard from a list of prediction dicts.

    Args:
        predictions: list of dicts with 'clv', 'clv_direction', 'sport', 'result', 'game_date'
        sport: optional sport filter
        window: rolling window size

    Returns:
        dict with rolling averages, trend, significance assessment
    """
    if sport:
        preds = [p for p in predictions if p.get("sport") == sport]
    else:
        preds = list(predictions)

    # Filter to those with CLV data
    preds = [p for p in preds if p.get("clv") is not None]

    if not preds:
        return {
            "total": 0,
            "avg_clv": None,
            "clv_hit_rate": None,
            "rolling": [],
            "significance": "insufficient_data",
            "trend": "flat",
        }

    # Sort by date
    preds.sort(key=lambda p: p.get("game_date", ""))

    total = len(preds)
    avg_clv = round(sum(p["clv"] for p in preds) / total, 3)
    clv_beats = sum(1 for p in preds if p.get("clv_direction") == 1)
    hit_rate = round(clv_beats / total * 100, 1)

    # Rolling window
    rolling = []
    for i in range(window, total + 1):
        batch = preds[i - window:i]
        batch_avg = sum(p["clv"] for p in batch) / len(batch)
        batch_beats = sum(1 for p in batch if p.get("clv_direction") == 1)
        rolling.append({
            "bet_number": i,
            "avg_clv": round(batch_avg, 3),
            "hit_rate": round(batch_beats / len(batch) * 100, 1),
        })

    # Significance test (one-sample t-test for CLV > 0)
    clv_values = [p["clv"] for p in preds]
    n = len(clv_values)
    if n >= 30:
        mean = sum(clv_values) / n
        variance = sum((x - mean) ** 2 for x in clv_values) / (n - 1)
        std_err = math.sqrt(variance / n) if variance > 0 else 1.0
        t_stat = mean / std_err if std_err > 0 else 0

        if t_stat > 2.0:
            significance = "significant_edge"
        elif t_stat > 1.5:
            significance = "marginal_edge"
        elif t_stat > 0:
            significance = "positive_but_noisy"
        else:
            significance = "no_edge"
    else:
        significance = "insufficient_data"

    # Trend: compare last 20 to overall
    if total >= 40:
        recent_avg = sum(p["clv"] for p in preds[-20:]) / 20
        trend = "improving" if recent_avg > avg_clv + 0.1 else (
            "declining" if recent_avg < avg_clv - 0.1 else "stable"
        )
    else:
        trend = "insufficient_data"

    # CLV vs win correlation
    graded = [p for p in preds if p.get("result") in ("win", "loss")]
    correlation = None
    if len(graded) >= 20:
        clv_vals = [p["clv"] for p in graded]
        result_vals = [1 if p["result"] == "win" else 0 for p in graded]
        n_g = len(clv_vals)
        mean_c = sum(clv_vals) / n_g
        mean_r = sum(result_vals) / n_g
        cov = sum((c - mean_c) * (r - mean_r) for c, r in zip(clv_vals, result_vals)) / n_g
        std_c = (sum((c - mean_c) ** 2 for c in clv_vals) / n_g) ** 0.5
        std_r = (sum((r - mean_r) ** 2 for r in result_vals) / n_g) ** 0.5
        if std_c > 0 and std_r > 0:
            correlation = round(cov / (std_c * std_r), 3)

    return {
        "total": total,
        "avg_clv": avg_clv,
        "clv_hit_rate": hit_rate,
        "rolling": rolling,
        "significance": significance,
        "trend": trend,
        "clv_result_correlation": correlation,
        "window": window,
    }
