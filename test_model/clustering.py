"""
Test Model Clustering — K-Means pattern clustering on standardized
feature subsets.  Provides cluster-level ATS hit rates and alignment
confidence based on distance to centroid.
Persists to disk via joblib for instant reload on restart.
"""

import os
import json
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import joblib

from test_model import db as tm_db
from test_model.features import FEATURE_COLUMNS, features_to_array

# Subset of features used for clustering (slot, spread, form, rest, rank)
CLUSTER_FEATURES = [
    "slot_public", "slot_vegas",
    "closing_spread", "spread_abs", "is_home_favorite",
    "line_movement_abs", "line_confirms_slot",
    "home_wins_last_7", "away_wins_last_7", "win_diff_last_7",
    "home_rest_days", "away_rest_days", "rest_advantage",
    "home_rank_filled", "away_rank_filled",
]

N_CLUSTERS = 12

# Module-level cache
_cluster_cache = {}

# Disk persistence directory
_ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tm_artifacts")
os.makedirs(_ARTIFACTS_DIR, exist_ok=True)


def _kmeans_path(sport):
    return os.path.join(_ARTIFACTS_DIR, f"kmeans_{sport}.joblib")


def _scaler_path(sport):
    return os.path.join(_ARTIFACTS_DIR, f"scaler_{sport}.joblib")


def _cluster_stats_path(sport):
    return os.path.join(_ARTIFACTS_DIR, f"cluster_stats_{sport}.json")


def save_clusters_to_disk(sport, result):
    """Persist trained clusters + scaler + stats to disk."""
    try:
        joblib.dump(result["kmeans"], _kmeans_path(sport))
        joblib.dump(result["scaler"], _scaler_path(sport))
        # Convert int keys to str for JSON
        stats = {str(k): v for k, v in result["cluster_stats"].items()}
        with open(_cluster_stats_path(sport), "w") as f:
            json.dump(stats, f)
    except Exception:
        pass


def load_clusters_from_disk(sport):
    """Load previously saved cluster model from disk. Returns result dict or None."""
    kp = _kmeans_path(sport)
    sp = _scaler_path(sport)
    cp = _cluster_stats_path(sport)
    if not os.path.exists(kp) or not os.path.exists(sp) or not os.path.exists(cp):
        return None
    try:
        kmeans = joblib.load(kp)
        scaler = joblib.load(sp)
        with open(cp, "r") as f:
            stats_raw = json.load(f)
        # Convert str keys back to int
        cluster_stats = {int(k): v for k, v in stats_raw.items()}
        result = {
            "kmeans": kmeans,
            "scaler": scaler,
            "cluster_stats": cluster_stats,
        }
        _cluster_cache[sport] = result
        return result
    except Exception:
        return None


def _get_cluster_indices():
    """Get indices of CLUSTER_FEATURES within FEATURE_COLUMNS."""
    return [FEATURE_COLUMNS.index(f) for f in CLUSTER_FEATURES if f in FEATURE_COLUMNS]


def train_clusters(sport, before_date=None):
    """
    Train K-Means clustering on historical features.

    Returns:
        Dict with {kmeans, scaler, cluster_stats} or None if insufficient data.
        cluster_stats: {cluster_id: {count, hits, hit_rate}}
    """
    rows = tm_db.get_game_features_for_training(sport, before_date)
    if len(rows) < 100:
        return None

    # Extract cluster feature subset
    indices = _get_cluster_indices()
    X = []
    targets = []
    for row in rows:
        full_arr = features_to_array(row)
        subset = [full_arr[i] for i in indices]
        X.append(subset)
        targets.append(row["_target"])

    X = np.array(X, dtype=np.float64)
    targets = np.array(targets)

    # Handle NaN
    X = np.nan_to_num(X, nan=0.0)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    n_clusters = min(N_CLUSTERS, len(X) // 10)
    if n_clusters < 2:
        n_clusters = 2

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10, max_iter=300)
    labels = kmeans.fit_predict(X_scaled)

    # Compute per-cluster stats
    cluster_stats = {}
    for i in range(n_clusters):
        mask = labels == i
        count = int(mask.sum())
        hits = int(targets[mask].sum())
        hit_rate = round(hits / count * 100, 1) if count > 0 else 0
        cluster_stats[i] = {"count": count, "hits": hits, "hit_rate": hit_rate}

    result = {
        "kmeans": kmeans,
        "scaler": scaler,
        "cluster_stats": cluster_stats,
    }

    _cluster_cache[sport] = result

    # Persist to disk (only for full training, not walk-forward backtest slices)
    if before_date is None:
        save_clusters_to_disk(sport, result)

    return result


def assign_cluster(features_dict, cluster_model):
    """
    Assign a game to a cluster.

    Args:
        features_dict: Feature dict (same schema as FEATURE_COLUMNS)
        cluster_model: Dict from train_clusters()

    Returns:
        Dict with {cluster_id, distance, hit_rate, alignment_confidence}
    """
    if cluster_model is None:
        return {"cluster_id": -1, "distance": 0, "hit_rate": 50.0, "alignment_confidence": 0}

    kmeans = cluster_model["kmeans"]
    scaler = cluster_model["scaler"]
    stats = cluster_model["cluster_stats"]

    indices = _get_cluster_indices()
    full_arr = features_to_array(features_dict)
    subset = np.array([[full_arr[i] for i in indices]], dtype=np.float64)
    subset = np.nan_to_num(subset, nan=0.0)
    subset_scaled = scaler.transform(subset)

    cluster_id = int(kmeans.predict(subset_scaled)[0])
    distance = float(np.min(np.linalg.norm(
        subset_scaled - kmeans.cluster_centers_[cluster_id], axis=0
    )))

    cluster_info = stats.get(cluster_id, {"hit_rate": 50.0})

    # Alignment confidence: inverse of distance (closer = stronger pattern match)
    # Normalize to 0-100 range
    alignment = max(0, min(100, round(100 / (1 + distance), 1)))

    return {
        "cluster_id": cluster_id,
        "distance": round(distance, 3),
        "hit_rate": cluster_info["hit_rate"],
        "alignment_confidence": alignment,
    }


def get_cached_clusters(sport):
    """Get clusters from memory cache, falling back to disk."""
    if sport in _cluster_cache:
        return _cluster_cache[sport]
    return load_clusters_from_disk(sport)
