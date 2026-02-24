"""
Test Model ML — GradientBoostingClassifier for ATS prediction.
Binary classification: home_covered=1 (HIT) vs 0 (MISS), pushes excluded.
Trained models persist to disk via joblib for instant reload on restart.
"""

import os
import json
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
import joblib

from test_model import db as tm_db
from test_model.features import FEATURE_COLUMNS, features_to_array

# Conservative params for 512MB budget
MODEL_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "min_samples_leaf": 20,
    "subsample": 0.8,
    "random_state": 42,
}

# Module-level model cache
_model_cache = {}

# Disk persistence directory
_ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tm_artifacts")
os.makedirs(_ARTIFACTS_DIR, exist_ok=True)


def _model_path(sport):
    return os.path.join(_ARTIFACTS_DIR, f"model_{sport}.joblib")


def _importances_path(sport):
    return os.path.join(_ARTIFACTS_DIR, f"importances_{sport}.json")


def save_model_to_disk(sport, result):
    """Persist trained model + importances to disk."""
    try:
        joblib.dump(result["model"], _model_path(sport))
        with open(_importances_path(sport), "w") as f:
            json.dump({
                "feature_importances": result["feature_importances"],
                "train_count": result["train_count"],
            }, f)
    except Exception:
        pass  # Non-fatal — memory cache still works


def load_model_from_disk(sport):
    """Load previously saved model from disk. Returns result dict or None."""
    mp = _model_path(sport)
    ip = _importances_path(sport)
    if not os.path.exists(mp) or not os.path.exists(ip):
        return None
    try:
        clf = joblib.load(mp)
        with open(ip, "r") as f:
            meta = json.load(f)
        result = {
            "model": clf,
            "feature_importances": meta.get("feature_importances", {}),
            "train_count": meta.get("train_count", 0),
        }
        _model_cache[sport] = result
        return result
    except Exception:
        return None


def train_model(sport, before_date=None):
    """
    Train GradientBoostingClassifier on historical features.

    Args:
        sport: Sport key
        before_date: Only use games before this date (for walk-forward)

    Returns:
        Dict with {model, feature_importances, train_count} or None
    """
    rows = tm_db.get_game_features_for_training(sport, before_date)
    if len(rows) < 100:
        return None

    X = []
    y = []
    for row in rows:
        arr = features_to_array(row)
        X.append(arr)
        y.append(row["_target"])

    X = np.array(X, dtype=np.float64)
    y = np.array(y)

    # Handle NaN
    X = np.nan_to_num(X, nan=0.0)

    clf = GradientBoostingClassifier(**MODEL_PARAMS)
    clf.fit(X, y)

    # Feature importances
    importances = {}
    for i, col in enumerate(FEATURE_COLUMNS):
        importances[col] = round(float(clf.feature_importances_[i]), 4)

    # Sort by importance
    importances = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))

    result = {
        "model": clf,
        "feature_importances": importances,
        "train_count": len(X),
    }

    _model_cache[sport] = result

    # Persist to disk (only for full training, not walk-forward backtest slices)
    if before_date is None:
        save_model_to_disk(sport, result)

    return result


def predict_game(model_dict, features_dict):
    """
    Predict P(home covers) for a single game.

    Args:
        model_dict: Dict from train_model()
        features_dict: Feature dict

    Returns:
        Float probability in [0, 1]
    """
    if model_dict is None:
        return 0.5

    clf = model_dict["model"]
    arr = np.array([features_to_array(features_dict)], dtype=np.float64)
    arr = np.nan_to_num(arr, nan=0.0)

    # P(home_covered=1)
    proba = clf.predict_proba(arr)[0]
    # Index of class 1
    classes = list(clf.classes_)
    idx = classes.index(1) if 1 in classes else 0
    return round(float(proba[idx]), 4)


def compute_edge_metrics(model_prob, closing_spread=None):
    """
    Compare model probability to closing line implied probability.

    At standard -110 vig, the implied probability of covering is ~52.38%.

    Returns:
        Dict with {closing_implied_prob, implied_edge, ev, projected_roi}
    """
    # Standard -110 vig: implied prob = 110/210 = 52.38%
    closing_implied = 0.5238

    implied_edge = round(model_prob - closing_implied, 4)

    # EV = (prob * payout) - (1-prob) * stake
    # At -110: win pays +100/110 = 0.909 units
    payout = 100 / 110  # 0.909
    ev = round(model_prob * payout - (1 - model_prob), 4)

    # Projected ROI = EV / 1 unit risked * 100
    projected_roi = round(ev * 100, 2)

    return {
        "closing_implied_prob": round(closing_implied, 4),
        "implied_edge": implied_edge,
        "ev": ev,
        "projected_roi": projected_roi,
    }


def get_cached_model(sport):
    """Get model from memory cache, falling back to disk."""
    if sport in _model_cache:
        return _model_cache[sport]
    return load_model_from_disk(sport)
