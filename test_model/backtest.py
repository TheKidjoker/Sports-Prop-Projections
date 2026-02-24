"""
Test Model Backtest — walk-forward backtesting engine.

Starts after minimum 500 training games, iterates test dates chronologically.
Retrains model every 30 days.  Runs as background thread with progress polling.
"""

import threading
from datetime import datetime

from test_model import db as tm_db
from test_model.model import train_model, predict_game, compute_edge_metrics
from test_model.clustering import train_clusters, assign_cluster
from test_model.metrics import compute_metrics

MIN_TRAINING_GAMES = 100  # Adaptive: works with smaller datasets, ideal is 500+
RETRAIN_INTERVAL_DAYS = 30

# Global progress dict for polling
_backtest_progress = {}
_backtest_lock = threading.Lock()


def get_backtest_status(sport):
    with _backtest_lock:
        return dict(_backtest_progress.get(sport, {}))


def run_backtest(sport):
    """
    Walk-forward backtest for a sport.  Runs synchronously.
    Call via start_backtest_thread() for background execution.
    """
    rows = tm_db.get_game_features_for_training(sport)
    if len(rows) < MIN_TRAINING_GAMES + 20:
        with _backtest_lock:
            _backtest_progress[sport] = {
                "status": "error",
                "message": f"Need at least {MIN_TRAINING_GAMES + 20} games with features, have {len(rows)}. Collect more data and compute features first.",
            }
        return

    # Find the date after MIN_TRAINING_GAMES
    start_idx = MIN_TRAINING_GAMES
    test_rows = rows[start_idx:]

    # Group test rows by date for retraining schedule
    all_dates = sorted(set(r["_game_date"] for r in test_rows))
    total_test = len(test_rows)

    with _backtest_lock:
        _backtest_progress[sport] = {
            "status": "running",
            "total_games": total_test,
            "processed": 0,
            "current_date": "",
        }

    predictions = []
    model_dict = None
    cluster_model = None
    last_train_date = None
    processed = 0

    for test_date in all_dates:
        with _backtest_lock:
            _backtest_progress[sport]["current_date"] = test_date

        # Retrain if needed
        needs_retrain = (
            model_dict is None
            or last_train_date is None
            or _days_apart(last_train_date, test_date) >= RETRAIN_INTERVAL_DAYS
        )

        if needs_retrain:
            model_dict = train_model(sport, before_date=test_date)
            cluster_model = train_clusters(sport, before_date=test_date)
            last_train_date = test_date

        if model_dict is None:
            continue

        # Predict each game on this date
        date_games = [r for r in test_rows if r["_game_date"] == test_date]
        for game in date_games:
            prob = predict_game(model_dict, game)
            actual = game["_target"]
            spread = game.get("closing_spread", 0)

            edge = compute_edge_metrics(prob, spread)

            cluster_info = {}
            if cluster_model:
                cluster_info = assign_cluster(game, cluster_model)

            predictions.append({
                "date": test_date,
                "model_prob": prob,
                "actual": actual,
                "spread": spread,
                "closing_implied_prob": edge["closing_implied_prob"],
                "implied_edge": edge["implied_edge"],
                "ev": edge["ev"],
                "projected_roi": edge["projected_roi"],
                "cluster_id": cluster_info.get("cluster_id", -1),
                "cluster_hit_rate": cluster_info.get("hit_rate", 50),
                "alignment_confidence": cluster_info.get("alignment_confidence", 0),
            })

            processed += 1
            with _backtest_lock:
                _backtest_progress[sport]["processed"] = processed

    # Compute final metrics
    metrics = compute_metrics(predictions)

    # Save model run
    tm_db.save_model_run({
        "sport": sport,
        "run_type": "backtest",
        "accuracy": metrics.get("accuracy"),
        "roi": metrics.get("roi"),
        "clv_avg": metrics.get("clv_avg"),
        "calibration_error": metrics.get("calibration_error"),
        "total_predictions": metrics.get("total_predictions"),
        "qualified_bets": metrics.get("qualified_bets"),
        "feature_importances": model_dict.get("feature_importances", {}) if model_dict else {},
        "model_params": {"min_training": MIN_TRAINING_GAMES, "retrain_days": RETRAIN_INTERVAL_DAYS},
        "threshold_analysis": metrics.get("threshold_analysis", {}),
        "predictions": predictions[-200:],  # Save last 200 for display
    })

    with _backtest_lock:
        _backtest_progress[sport] = {
            "status": "complete",
            "total_games": total_test,
            "processed": processed,
            "current_date": "",
            "metrics": metrics,
        }

    return metrics


def _days_apart(date_str1, date_str2):
    """Approximate days between two date strings."""
    try:
        d1 = datetime.fromisoformat(date_str1.replace("Z", "+00:00"))
        d2 = datetime.fromisoformat(date_str2.replace("Z", "+00:00"))
        return abs((d2 - d1).days)
    except (ValueError, TypeError, AttributeError):
        return 999


def start_backtest_thread(sport):
    """Start backtest in a background thread.  Returns immediately."""
    with _backtest_lock:
        existing = _backtest_progress.get(sport, {})
        if existing.get("status") == "running":
            return False

    t = threading.Thread(target=run_backtest, args=(sport,), daemon=True)
    t.start()
    return True
