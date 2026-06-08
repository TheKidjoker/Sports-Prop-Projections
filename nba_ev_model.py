"""
NBA EV Model — L2-regularized logistic regression for NBA spread prediction.

Replaces the heuristic additive scoring system (49% OOS) with a calibrated
probability model that feeds an EV-based betting framework:
    Edge = Model_Probability - Implied_Market_Probability

Features (11):
    spread_abs, clv, rest_diff,
    dog_off_regressed, fav_off_regressed, net_rating_diff,
    dog_win_pct_10, fav_win_pct_10, home_away, elo_diff, pace_diff

Removed (collinear): days_rest_dog, days_rest_fav (with rest_diff),
    spread_squared (with spread_abs)
Added: elo_diff (Elo power rating difference), pace_diff (over/under delta)

Training: strict chronological 70/30 split, no shuffling, StandardScaler
fitted on train only.  AUC gate: reject if AUC < 0.60.
Walk-forward: 500-train/100-test/step-100 with Brier score per fold.
"""

import math
import threading
import numpy as np
from collections import defaultdict

from constants import EV_CONFIG
from test_model.date_utils import parse_iso_date

# ─── Module-level model cache ────────────────────────────────────────────────

_nba_ev_cache = {
    "model": None,
    "scaler_mean": [],
    "scaler_std": [],
    "feature_names": [],
    "auc": None,
    "is_valid": False,
    "platt": None,
    "coefficients": {},
}

# ─── Training progress (for polling) ─────────────────────────────────────────

_ev_progress = {}
_ev_lock = threading.Lock()


def get_ev_training_status():
    with _ev_lock:
        return dict(_ev_progress)


# ─── Feature Engineering ─────────────────────────────────────────────────────

def _regressed_avg(all_scores, recent_n=5, prior_weight=None):
    """Blend recent games with season average via Bayesian shrinkage.

    Shrinks recent performance toward season average to reduce noise.
    With prior_weight=15: at 5 recent games, season avg gets 75% weight;
    at 20 recent games, season avg gets 43% weight.
    """
    if prior_weight is None:
        prior_weight = EV_CONFIG["regressed_prior_weight"]
    default = EV_CONFIG["league_avg_score"]
    if not all_scores:
        return default
    season_avg = sum(all_scores) / len(all_scores)
    recent = all_scores[-recent_n:] if len(all_scores) >= recent_n else all_scores
    recent_avg = sum(recent) / len(recent)
    n_recent = len(recent)
    return (n_recent * recent_avg + prior_weight * season_avg) / (n_recent + prior_weight)


def _extract_features(game, team_state, feature_names):
    """
    Extract feature vector for one game from pre-built team state.

    Args:
        game: dict with closing_spread, opening_spread, over_under, home_team, away_team
        team_state: dict of team_name -> state dict
        feature_names: ordered list of feature names

    Returns:
        dict of feature_name -> value, or None if features can't be computed
    """
    closing = game.get("closing_spread")
    opening = game.get("opening_spread")
    over_under = game.get("over_under")

    if closing is None:
        return None

    # Identify dog/fav (negative spread = home favored, dog = away)
    if closing < 0:
        fav_team = game["home_team"]
        dog_team = game["away_team"]
    else:
        fav_team = game["away_team"]
        dog_team = game["home_team"]

    fav_st = team_state.get(fav_team)
    dog_st = team_state.get(dog_team)

    if not fav_st or not dog_st:
        return None
    if len(fav_st.get("scores", [])) < 5 or len(dog_st.get("scores", [])) < 5:
        return None

    # Feature 1: spread_abs
    spread_abs = abs(closing)

    # Feature 2: clv (closing line value from dog perspective)
    if opening is not None:
        clv = closing - opening  # positive = line moved toward dog
        if closing > 0:
            clv = -clv  # normalize: away favored case
    else:
        clv = 0.0

    # Feature 3: rest_diff (dog_rest - fav_rest)
    game_date_str = game.get("game_date", "")
    dog_rest = _days_since_last(dog_st, game_date_str)
    fav_rest = _days_since_last(fav_st, game_date_str)
    rest_diff = dog_rest - fav_rest

    # Features 4-5: regressed offensive efficiency
    dog_off_regressed = _regressed_avg(dog_st["scores"])
    fav_off_regressed = _regressed_avg(fav_st["scores"])

    # Feature 6: net_rating_diff
    dog_def = _regressed_avg(dog_st.get("opp_scores", []))
    fav_def = _regressed_avg(fav_st.get("opp_scores", []))
    dog_net = dog_off_regressed - dog_def
    fav_net = fav_off_regressed - fav_def
    net_rating_diff = dog_net - fav_net

    # Features 7-8: win pct last 10
    dog_win_pct_10 = _win_pct_last_n(dog_st, 10)
    fav_win_pct_10 = _win_pct_last_n(fav_st, 10)

    # Feature 9: home_away (1 if underdog is home team, 0 if away)
    home_away = 1.0 if closing > 0 else 0.0

    # Feature 10: elo_diff (Elo rating difference, dog - fav perspective)
    from constants import USE_ELO_FEATURES
    if USE_ELO_FEATURES:
        try:
            from power_ratings import get_elo
            dog_elo = get_elo(dog_team, "nba")
            fav_elo = get_elo(fav_team, "nba")
            elo_diff = (dog_elo - fav_elo) / 100.0  # Scale to ~[-5, 5]
        except Exception:
            elo_diff = 0.0
    else:
        elo_diff = 0.0

    # Feature 11: pace_diff (over/under deviation from league avg)
    over_under = game.get("over_under")
    league_avg_total = EV_CONFIG["league_avg_score"] * 2  # ~210
    if over_under is not None:
        pace_diff = (over_under - league_avg_total) / 10.0  # Scale to ~[-2, 2]
    else:
        pace_diff = 0.0

    features = {
        "spread_abs": spread_abs,
        "clv": clv,
        "rest_diff": rest_diff,
        "dog_off_regressed": dog_off_regressed,
        "fav_off_regressed": fav_off_regressed,
        "net_rating_diff": net_rating_diff,
        "dog_win_pct_10": dog_win_pct_10,
        "fav_win_pct_10": fav_win_pct_10,
        "home_away": home_away,
        "elo_diff": elo_diff,
        "pace_diff": pace_diff,
    }
    return features


def _days_since_last(team_st, game_date_str):
    """Days since team's last game. Returns 3 if unknown."""
    if not team_st.get("dates"):
        return 3
    last_dt = parse_iso_date(team_st["dates"][-1])
    game_dt = parse_iso_date(game_date_str)
    if last_dt is None or game_dt is None:
        return 3
    diff = abs((game_dt - last_dt).days)
    return min(diff, 7)  # Cap at 7 to avoid outliers (all-star break etc.)


def _win_pct_last_n(team_st, n=10):
    """Win percentage over last N games. Returns 0.5 if insufficient data."""
    results = team_st.get("results", [])
    if len(results) < 3:
        return 0.5
    recent = results[-n:] if len(results) >= n else results
    return sum(recent) / len(recent)


# ─── Dataset Builder ─────────────────────────────────────────────────────────

def build_nba_ev_dataset():
    """
    Build chronological dataset from tm_historical_games for NBA.

    Returns:
        list of (features_dict, target) tuples sorted chronologically.
        target: 1 if underdog covered, 0 if not.
    """
    from test_model import db as tm_db

    games = tm_db.get_historical_games("nba")
    if not games:
        return []

    # Filter to final games with spread
    eligible = [
        g for g in games
        if g.get("closing_spread") is not None
        and g.get("home_covered") in (0, 1)
        and g.get("game_status") == "STATUS_FINAL"
    ]

    # Sort chronologically
    eligible.sort(key=lambda g: g.get("game_date", ""))

    warmup = EV_CONFIG["warmup_games"]
    window = EV_CONFIG["rolling_window"]
    feature_names = EV_CONFIG["feature_names"]

    team_state = {}
    dataset = []

    for i, game in enumerate(eligible):
        home = game["home_team"]
        away = game["away_team"]

        # Ensure team state exists
        for t in (home, away):
            if t not in team_state:
                team_state[t] = {
                    "scores": [], "opp_scores": [], "results": [],
                    "dates": [],
                }

        # Skip warmup period (need team history)
        if i >= warmup:
            features = _extract_features(game, team_state, feature_names)
            if features is not None:
                # Target: underdog covered
                closing = game["closing_spread"]
                home_covered = game["home_covered"]
                if closing < 0:
                    # Home favored → underdog is away → underdog covered = home did NOT cover
                    target = 1 - home_covered
                else:
                    # Away favored → underdog is home → underdog covered = home covered
                    target = home_covered
                dataset.append((features, target))

        # Update team state AFTER feature extraction
        _update_team_state_ev(game, team_state, window)

    return dataset


def _update_team_state_ev(game, team_state, window):
    """Update team state with game results, trimmed to rolling window."""
    home = game["home_team"]
    away = game["away_team"]
    home_score = game.get("home_score", 0) or 0
    away_score = game.get("away_score", 0) or 0
    home_won = 1 if home_score > away_score else 0
    game_date = game.get("game_date", "")

    for t in (home, away):
        if t not in team_state:
            team_state[t] = {
                "scores": [], "opp_scores": [], "results": [], "dates": [],
            }

    team_state[home]["scores"].append(home_score)
    team_state[home]["opp_scores"].append(away_score)
    team_state[home]["results"].append(home_won)
    team_state[home]["dates"].append(game_date)

    team_state[away]["scores"].append(away_score)
    team_state[away]["opp_scores"].append(home_score)
    team_state[away]["results"].append(1 - home_won)
    team_state[away]["dates"].append(game_date)

    # Trim to window
    for t in (home, away):
        for key in ("scores", "opp_scores", "results", "dates"):
            if len(team_state[t][key]) > window:
                team_state[t][key] = team_state[t][key][-window:]


# ─── Training ────────────────────────────────────────────────────────────────

def train_nba_ev_model(dataset, mode="split"):
    """
    Train L2-regularized logistic regression on NBA dataset.

    Args:
        dataset: list of (features_dict, target) tuples
        mode: "split" (70/30 chrono) or "rolling" (350/50 windows)

    Returns:
        dict with model params, metrics, edge buckets, or error info
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, brier_score_loss

    if len(dataset) < 100:
        return {"error": f"Insufficient data: {len(dataset)} games (need 100+)"}

    feature_names = EV_CONFIG["feature_names"]

    # Build arrays
    X = np.array([[d[0][f] for f in feature_names] for d in dataset], dtype=float)
    y = np.array([d[1] for d in dataset], dtype=float)

    if mode == "split":
        return _train_split(X, y, feature_names)
    elif mode == "rolling":
        return _train_rolling(X, y, feature_names)
    else:
        return {"error": f"Unknown mode: {mode}"}


def _train_split(X, y, feature_names):
    """70/30 chronological split training."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, brier_score_loss

    split_pct = EV_CONFIG["train_split"]
    split_idx = int(len(X) * split_pct)

    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    # Fit scaler on train only
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    # Train model
    C = EV_CONFIG["regularization_C"]
    model = LogisticRegression(
        penalty="l2", C=C, solver="lbfgs", max_iter=1000, random_state=42,
    )
    model.fit(X_train_s, y_train)

    # Predict on test set
    y_prob = model.predict_proba(X_test_s)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    # Metrics
    auc = roc_auc_score(y_test, y_prob)
    brier = brier_score_loss(y_test, y_prob)
    accuracy = np.mean(y_pred == y_test) * 100

    # Coefficients
    coefficients = {}
    for i, name in enumerate(feature_names):
        coefficients[name] = round(float(model.coef_[0][i]), 4)
    coefficients["intercept"] = round(float(model.intercept_[0]), 4)

    # Edge bucket analysis
    edge_buckets = _compute_edge_buckets(y_prob, y_test)
    monotonic = _check_monotonicity(edge_buckets)

    # Check ECE for Platt scaling need
    ece = _compute_ece(y_prob, y_test)
    platt_params = None
    if ece > 5.0:
        platt_params = _fit_platt(y_prob, y_test)

    # AUC gate check
    auc_gate = EV_CONFIG["auc_gate"]
    is_valid = auc >= auc_gate

    result = {
        "mode": "split",
        "is_valid": is_valid,
        "auc": round(auc, 4),
        "auc_gate": auc_gate,
        "brier_score": round(brier, 4),
        "accuracy": round(accuracy, 2),
        "train_size": len(X_train),
        "test_size": len(X_test),
        "coefficients": coefficients,
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_std": scaler.scale_.tolist(),
        "feature_names": feature_names,
        "edge_buckets": edge_buckets,
        "monotonicity_pass": monotonic,
        "ece": round(ece, 2),
        "platt_params": platt_params,
        "base_rate_train": round(float(np.mean(y_train)) * 100, 2),
        "base_rate_test": round(float(np.mean(y_test)) * 100, 2),
    }

    # Load into cache if valid
    if is_valid:
        _load_model_to_cache(result)

    return result


def _train_rolling(X, y, feature_names):
    """Rolling window validation: 500-train / 100-test, step 100."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, brier_score_loss

    train_size = 500
    test_size = 100
    step = 100
    C = EV_CONFIG["regularization_C"]

    fold_aucs = []
    fold_accuracies = []
    fold_briers = []
    all_y_prob = []
    all_y_true = []

    i = 0
    while i + train_size + test_size <= len(X):
        X_train = X[i:i + train_size]
        y_train = y[i:i + train_size]
        X_test = X[i + train_size:i + train_size + test_size]
        y_test = y[i + train_size:i + train_size + test_size]

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        model = LogisticRegression(
            penalty="l2", C=C, solver="lbfgs", max_iter=1000, random_state=42,
        )
        model.fit(X_train_s, y_train)

        y_prob = model.predict_proba(X_test_s)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)

        try:
            fold_auc = roc_auc_score(y_test, y_prob)
            fold_aucs.append(fold_auc)
        except ValueError:
            pass

        fold_acc = np.mean(y_pred == y_test) * 100
        fold_accuracies.append(fold_acc)

        fold_brier = brier_score_loss(y_test, y_prob)
        fold_briers.append(fold_brier)

        all_y_prob.extend(y_prob.tolist())
        all_y_true.extend(y_test.tolist())

        i += step

    if not fold_aucs:
        return {"error": "No valid folds in rolling validation"}

    mean_auc = np.mean(fold_aucs)
    std_auc = np.std(fold_aucs)
    mean_acc = np.mean(fold_accuracies)
    mean_brier = np.mean(fold_briers)

    # ROI computation on all OOS predictions
    all_y_prob_arr = np.array(all_y_prob)
    all_y_true_arr = np.array(all_y_true)

    # Edge buckets on all OOS predictions
    edge_buckets = _compute_edge_buckets(all_y_prob_arr, all_y_true_arr)
    monotonic = _check_monotonicity(edge_buckets)

    # Overall OOS ROI (betting on all positive-edge predictions at -110)
    implied = EV_CONFIG["implied_prob"]
    edges = all_y_prob_arr - implied
    positive_mask = edges > 0
    if np.sum(positive_mask) > 0:
        pos_wins = int(np.sum(all_y_true_arr[positive_mask]))
        pos_n = int(np.sum(positive_mask))
        pos_losses = pos_n - pos_wins
        oos_roi = round(((pos_wins * (100 / 110) - pos_losses) / pos_n) * 100, 2)
    else:
        oos_roi = 0.0

    # Wilson CI on OOS accuracy
    from constants import wilson_interval
    total_correct = int(np.sum((all_y_prob_arr >= 0.5) == all_y_true_arr))
    total_n = len(all_y_true_arr)
    acc_ci = wilson_interval(total_correct, total_n)

    return {
        "mode": "rolling",
        "is_valid": mean_auc >= EV_CONFIG["auc_gate"],
        "mean_auc": round(float(mean_auc), 4),
        "std_auc": round(float(std_auc), 4),
        "auc_gate": EV_CONFIG["auc_gate"],
        "mean_accuracy": round(float(mean_acc), 2),
        "accuracy_ci": {"lower": acc_ci[0], "upper": acc_ci[1]},
        "mean_brier": round(float(mean_brier), 4),
        "oos_roi": oos_roi,
        "n_folds": len(fold_aucs),
        "fold_aucs": [round(a, 4) for a in fold_aucs],
        "fold_briers": [round(b, 4) for b in fold_briers],
        "oos_predictions": len(all_y_prob),
        "edge_buckets": edge_buckets,
        "monotonicity_pass": monotonic,
    }


# ─── Edge Bucket Analysis ────────────────────────────────────────────────────

def _compute_edge_buckets(y_prob, y_actual):
    """Compute ROI and accuracy per edge bucket."""
    implied = EV_CONFIG["implied_prob"]
    edges = y_prob - implied

    bucket_defs = [
        ("0-2%", 0.00, 0.02),
        ("2-4%", 0.02, 0.04),
        ("4-6%", 0.04, 0.06),
        ("6-8%", 0.06, 0.08),
        ("8%+", 0.08, 1.00),
    ]

    buckets = []
    for label, lo, hi in bucket_defs:
        mask = (edges >= lo) & (edges < hi)
        n = int(np.sum(mask))
        if n == 0:
            buckets.append({
                "label": label, "count": 0,
                "accuracy": 0, "roi": 0, "avg_edge": 0,
            })
            continue

        wins = int(np.sum(y_actual[mask]))
        losses = n - wins
        acc = round(wins / n * 100, 2)
        roi = round(((wins * (100 / 110) - losses) / n) * 100, 2)
        avg_edge = round(float(np.mean(edges[mask])) * 100, 2)

        buckets.append({
            "label": label, "count": n,
            "accuracy": acc, "roi": roi, "avg_edge": avg_edge,
        })

    return buckets


def _check_monotonicity(edge_buckets):
    """Check if ROI increases monotonically across populated buckets."""
    populated = [b for b in edge_buckets if b["count"] >= 5]
    if len(populated) < 2:
        return True  # Not enough data to test
    for i in range(1, len(populated)):
        if populated[i]["roi"] < populated[i - 1]["roi"]:
            return False
    return True


# ─── ECE and Platt Scaling ───────────────────────────────────────────────────

def _compute_ece(y_prob, y_actual, n_bins=10):
    """Expected Calibration Error as percentage."""
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    total = len(y_prob)
    for i in range(n_bins):
        mask = (y_prob >= bin_edges[i]) & (y_prob < bin_edges[i + 1])
        n = int(np.sum(mask))
        if n > 0:
            avg_pred = float(np.mean(y_prob[mask]))
            avg_actual = float(np.mean(y_actual[mask]))
            ece += (n / total) * abs(avg_pred - avg_actual)
    return round(ece * 100, 2)


def _fit_platt(y_prob, y_actual):
    """Fit Platt scaling: secondary logistic on log-odds of predictions."""
    from sklearn.linear_model import LogisticRegression

    # Convert to log-odds
    eps = 1e-7
    y_prob_clipped = np.clip(y_prob, eps, 1 - eps)
    log_odds = np.log(y_prob_clipped / (1 - y_prob_clipped))

    platt_model = LogisticRegression(
        penalty="l2", C=1.0, solver="lbfgs", max_iter=1000,
    )
    platt_model.fit(log_odds.reshape(-1, 1), y_actual)

    return {
        "coef": round(float(platt_model.coef_[0][0]), 6),
        "intercept": round(float(platt_model.intercept_[0]), 6),
    }


def _apply_platt(prob, platt_params):
    """Apply Platt scaling to a raw probability."""
    if platt_params is None:
        return prob
    eps = 1e-7
    p = max(eps, min(1 - eps, prob))
    log_odds = math.log(p / (1 - p))
    z = platt_params["coef"] * log_odds + platt_params["intercept"]
    return 1 / (1 + math.exp(-z))


# ─── EV Computation ──────────────────────────────────────────────────────────

def compute_ev(model_prob):
    """
    Compute edge and EV per unit at -110 odds.

    Returns:
        (edge, ev_per_unit) tuple
        edge: model_prob - implied_prob (positive = value)
        ev_per_unit: expected cents profit per $1 wagered
    """
    implied = EV_CONFIG["implied_prob"]
    edge = model_prob - implied
    ev_per_unit = model_prob * (100 / 110) - (1 - model_prob)
    return round(edge, 4), round(ev_per_unit, 4)


def get_ev_recommendation(model_prob):
    """Map model probability to recommendation tier based on edge."""
    edge = model_prob - EV_CONFIG["implied_prob"]
    tiers = EV_CONFIG["edge_tiers"]
    if edge >= tiers["strong"]:
        return "STRONG PLAY"
    if edge >= tiers["confident"]:
        return "CONFIDENT"
    if edge >= tiers["lean"]:
        return "LEAN"
    return "MONITOR"


# ─── Model Cache Management ─────────────────────────────────────────────────

def _load_model_to_cache(result):
    """Load trained model parameters into the module-level cache."""
    global _nba_ev_cache
    _nba_ev_cache = {
        "model": None,  # We reconstruct from coefficients
        "scaler_mean": result["scaler_mean"],
        "scaler_std": result["scaler_std"],
        "feature_names": result["feature_names"],
        "auc": result["auc"],
        "is_valid": result["is_valid"],
        "platt": result.get("platt_params"),
        "coefficients": result["coefficients"],
    }
    print(f"[nba_ev] Model loaded — AUC: {result['auc']}, valid: {result['is_valid']}", flush=True)


def load_nba_ev_model(model_params):
    """
    Load a previously saved EV model from model_params dict.
    Called at app startup from tm_model_runs.
    """
    global _nba_ev_cache

    auc = model_params.get("auc", 0)
    is_valid = auc >= EV_CONFIG["auc_gate"]

    _nba_ev_cache = {
        "model": None,
        "scaler_mean": model_params.get("scaler_mean", []),
        "scaler_std": model_params.get("scaler_std", []),
        "feature_names": model_params.get("feature_names", EV_CONFIG["feature_names"]),
        "auc": auc,
        "is_valid": is_valid,
        "platt": model_params.get("platt_params"),
        "coefficients": model_params.get("coefficients", {}),
    }
    if is_valid:
        print(f"[nba_ev] Model restored from DB — AUC: {auc}", flush=True)
    else:
        print(f"[nba_ev] Model loaded but below AUC gate ({auc} < {EV_CONFIG['auc_gate']})", flush=True)


def is_ev_model_active():
    """Check if EV model is loaded and valid."""
    return _nba_ev_cache.get("is_valid", False)


def predict_single(features_dict):
    """
    Predict underdog cover probability for a single game.

    Args:
        features_dict: dict with all feature values

    Returns:
        dict with probability, edge, ev, recommendation, or None if model inactive
    """
    if not is_ev_model_active():
        return None

    cache = _nba_ev_cache
    feature_names = cache["feature_names"]
    coefs = cache["coefficients"]
    scaler_mean = cache["scaler_mean"]
    scaler_std = cache["scaler_std"]

    if not coefs or not scaler_mean or not scaler_std:
        return None
    if len(scaler_mean) != len(feature_names):
        return None

    # Build feature vector
    try:
        x = np.array([features_dict.get(f, 0.0) for f in feature_names], dtype=float)
    except (ValueError, TypeError):
        return None

    # Scale
    x_scaled = (x - np.array(scaler_mean)) / np.array(scaler_std)

    # Manual logistic regression: z = X @ coef + intercept
    intercept = coefs.get("intercept", 0)
    coef_vals = np.array([coefs.get(f, 0) for f in feature_names])
    z = float(np.dot(x_scaled, coef_vals) + intercept)

    # Sigmoid
    prob = 1 / (1 + math.exp(-z))

    # Apply Platt scaling if available
    if cache.get("platt"):
        prob = _apply_platt(prob, cache["platt"])

    edge, ev_per_unit = compute_ev(prob)
    recommendation = get_ev_recommendation(prob)

    # Confirmation score for backward-compatible sorting
    confirmation_score = max(0, int((prob - 0.5) * 100))

    return {
        "model_probability": round(prob * 100, 1),
        "edge": round(edge * 100, 1),
        "ev_per_unit": round(ev_per_unit * 100, 1),
        "recommendation": recommendation,
        "confirmation_score": confirmation_score,
        "auc": cache["auc"],
        "active": True,
    }


# ─── Live Feature Extraction ─────────────────────────────────────────────────

# Team state cache for live games (loaded from historical DB)
_live_team_state = {}
_live_state_loaded = False


def load_live_team_state():
    """Populate team_state from historical DB for live feature extraction."""
    global _live_team_state, _live_state_loaded
    try:
        from test_model import db as tm_db
        games = tm_db.get_historical_games("nba")
        if not games:
            return

        eligible = [
            g for g in games
            if g.get("game_status") == "STATUS_FINAL"
            and g.get("home_score") is not None
        ]
        eligible.sort(key=lambda g: g.get("game_date", ""))

        team_state = {}
        window = EV_CONFIG["rolling_window"]
        for game in eligible:
            _update_team_state_ev(game, team_state, window)

        _live_team_state = team_state
        _live_state_loaded = True
        print(f"[nba_ev] Live team state loaded: {len(team_state)} teams", flush=True)
    except Exception as e:
        print(f"[nba_ev] Failed to load live team state: {e}", flush=True)


def _ensure_live_state():
    """Lazy-load team state on first use instead of at startup."""
    if not _live_state_loaded:
        load_live_team_state()


def extract_live_features(current_spread, opening_spread, over_under,
                          home_team, away_team, game_date_str):
    """
    Extract features for a live game using cached team state.

    Returns:
        features_dict or None
    """
    _ensure_live_state()
    if not _live_state_loaded:
        return None

    game = {
        "closing_spread": current_spread,
        "opening_spread": opening_spread,
        "over_under": over_under,
        "home_team": home_team,
        "away_team": away_team,
        "game_date": game_date_str,
    }

    return _extract_features(game, _live_team_state, EV_CONFIG["feature_names"])


# ─── Full Training Pipeline ──────────────────────────────────────────────────

def run_full_training():
    """
    Full training pipeline: build dataset → train → test monotonicity → save.
    Runs synchronously. Call via start_ev_training_thread() for background.
    """
    from test_model import db as tm_db

    with _ev_lock:
        _ev_progress.update({
            "status": "building_dataset",
            "message": "Building feature dataset from historical games...",
        })

    # Build dataset
    dataset = build_nba_ev_dataset()
    if not dataset:
        with _ev_lock:
            _ev_progress.update({
                "status": "error",
                "message": "No dataset could be built. Collect more NBA historical data.",
            })
        return

    with _ev_lock:
        _ev_progress.update({
            "status": "training",
            "message": f"Training on {len(dataset)} games (70/30 split)...",
            "dataset_size": len(dataset),
        })

    # Train split model
    split_result = train_nba_ev_model(dataset, mode="split")
    if "error" in split_result:
        with _ev_lock:
            _ev_progress.update({
                "status": "error",
                "message": split_result["error"],
            })
        return

    with _ev_lock:
        _ev_progress.update({
            "status": "validating",
            "message": "Running rolling validation...",
            "split_auc": split_result["auc"],
        })

    # Train rolling model for cross-validation
    rolling_result = train_nba_ev_model(dataset, mode="rolling")

    with _ev_lock:
        _ev_progress.update({
            "status": "saving",
            "message": "Saving model results...",
        })

    # Save to DB
    tm_db.save_model_run({
        "sport": "nba",
        "run_type": "ev_logistic",
        "accuracy": split_result.get("accuracy"),
        "roi": None,
        "total_predictions": split_result.get("test_size", 0),
        "qualified_bets": split_result.get("test_size", 0),
        "model_params": {
            "auc": split_result["auc"],
            "brier_score": split_result.get("brier_score"),
            "coefficients": split_result["coefficients"],
            "scaler_mean": split_result["scaler_mean"],
            "scaler_std": split_result["scaler_std"],
            "feature_names": split_result["feature_names"],
            "edge_buckets": split_result["edge_buckets"],
            "monotonicity_pass": split_result["monotonicity_pass"],
            "ece": split_result.get("ece"),
            "platt_params": split_result.get("platt_params"),
            "is_valid": split_result["is_valid"],
            "rolling_validation": rolling_result if "error" not in rolling_result else None,
        },
        "feature_importances": split_result["coefficients"],
        "threshold_analysis": {
            "edge_buckets": split_result["edge_buckets"],
        },
    })

    # Load live team state if model is valid
    if split_result["is_valid"]:
        load_live_team_state()

    with _ev_lock:
        _ev_progress.update({
            "status": "complete",
            "message": "Training complete.",
            "split_result": split_result,
            "rolling_result": rolling_result if "error" not in rolling_result else None,
        })

    return split_result


def start_ev_training_thread():
    """Start EV training in a background thread. Returns immediately."""
    with _ev_lock:
        if _ev_progress.get("status") == "running":
            return False
        _ev_progress.update({"status": "running", "message": "Starting..."})

    t = threading.Thread(target=run_full_training, daemon=True)
    t.start()
    return True
