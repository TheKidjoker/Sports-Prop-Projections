"""
Test Model Scanner — runs model predictions on today's games,
overlaying ML probability, edge, EV, cluster alignment, and sentiment
onto the existing rules-based scan results.
"""

import time
from datetime import datetime, timezone

from game_scanner import scan_all_games
from test_model.model import train_model, predict_game, compute_edge_metrics, get_cached_model
from test_model.clustering import train_clusters, assign_cluster, get_cached_clusters
from test_model.features import compute_live_features
from test_model.sentiment import get_game_sentiment
from test_model import db as tm_db

# Cache model for up to 24 hours
_live_model_cache = {}
_CACHE_TTL = 24 * 3600


def _get_or_train_model(sport):
    """Load/cache trained model.  Retrain if stale (>24hr)."""
    cached = _live_model_cache.get(sport)
    if cached and (time.time() - cached["ts"]) < _CACHE_TTL:
        return cached["model"], cached["clusters"]

    # Try disk-cached artifacts first (instant load)
    model_dict = get_cached_model(sport)
    cluster_model = get_cached_clusters(sport)

    # Fall back to training if no disk artifacts
    if model_dict is None:
        model_dict = train_model(sport)
    if cluster_model is None:
        cluster_model = train_clusters(sport)

    if model_dict:
        _live_model_cache[sport] = {
            "model": model_dict,
            "clusters": cluster_model,
            "ts": time.time(),
        }

    return model_dict, cluster_model


def scan_today_with_model(sport):
    """
    Run existing rules-based scan, then overlay ML model predictions.

    Returns:
        List of game analysis dicts, each augmented with:
            model_prob, model_edge, model_ev, model_roi,
            cluster_id, cluster_hit_rate, alignment_confidence,
            sentiment
    """
    # Step 1: Rules-based scan
    games = scan_all_games(sport)
    if not games:
        return []

    # Step 2: Load/train model
    model_dict, cluster_model = _get_or_train_model(sport)

    if model_dict is None:
        # No model available yet — return games with empty overlay
        for g in games:
            g["tm_overlay"] = {"available": False, "reason": "Model not trained yet"}
        return games

    # Step 3: For each game, compute features + predict
    for g in games:
        if g.get("skip"):
            g["tm_overlay"] = {"available": False, "reason": "skip"}
            continue

        try:
            # Sentiment (live only, graceful if unavailable)
            sentiment = get_game_sentiment(g["home_team"], g["away_team"])

            # Compute live features
            features = compute_live_features(g, sport, sentiment)

            # Model prediction
            prob = predict_game(model_dict, features)
            edge = compute_edge_metrics(prob, g.get("current_spread"))

            # Cluster assignment
            cluster_info = {}
            if cluster_model:
                cluster_info = assign_cluster(features, cluster_model)

            g["tm_overlay"] = {
                "available": True,
                "model_prob": prob,
                "model_edge": edge["implied_edge"],
                "model_ev": edge["ev"],
                "model_roi": edge["projected_roi"],
                "closing_implied_prob": edge["closing_implied_prob"],
                "cluster_id": cluster_info.get("cluster_id", -1),
                "cluster_hit_rate": cluster_info.get("hit_rate", 50),
                "alignment_confidence": cluster_info.get("alignment_confidence", 0),
                "sentiment": sentiment,
            }

        except Exception as e:
            g["tm_overlay"] = {"available": False, "reason": str(e)}

    return games
