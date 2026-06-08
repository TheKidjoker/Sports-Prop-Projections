"""
MLB EV Model — L2-regularized logistic regression for MLB moneyline prediction.

Key difference from NHL/NBA: MLB uses moneyline (not spreads), so the target
variable is "dog won outright" rather than "underdog covered the spread."
Starting pitchers dominate outcomes, B2B is irrelevant (162-game daily schedule),
and scoring is Poisson-distributed.

Features (9):
    moneyline_implied, clv, line_movement_abs,
    dog_runs_regressed, fav_runs_regressed, run_diff_net,
    total, elo_diff, home_away

Training: walk-forward rolling only (300-train / 75-test, step 75).
AUC gate: reject if AUC < 0.55.
Edge tiers: STRONG 6%+, CONFIDENT 4%+, LEAN 2%+.
"""

import math
import threading
import numpy as np

from test_model.date_utils import parse_iso_date

# ─── MLB-Specific Configuration ─────────────────────────────────────────────

MLB_EV_CONFIG = {
    "auc_gate": 0.55,
    "implied_prob": 110 / (100 + 110),  # 0.5238 at -110
    "edge_tiers": {
        "strong": 0.06,
        "confident": 0.04,
        "lean": 0.02,
    },
    "regularization_C": 0.05,
    "warmup_games": 30,
    "rolling_window": 30,
    "regressed_prior_weight": 20,
    "league_avg_runs": 4.5,
    "default_total": 8.5,
    "feature_names": [
        "moneyline_implied", "clv", "line_movement_abs",
        "dog_runs_regressed", "fav_runs_regressed", "run_diff_net",
        "total", "elo_diff", "home_away",
    ],
    "rolling_train_size": 300,
    "rolling_test_size": 75,
    "rolling_step": 75,
}

# ─── Module-level model cache ────────────────────────────────────────────────

_mlb_ev_cache = {
    "model": None,
    "scaler_mean": [],
    "scaler_std": [],
    "feature_names": [],
    "auc": None,
    "is_valid": False,
    "platt": None,
    "coefficients": {},
}

# ─── Training progress ──────────────────────────────────────────────────────

_ev_progress = {}
_ev_lock = threading.Lock()


def get_ev_training_status():
    with _ev_lock:
        return dict(_ev_progress)


# ─── Feature Engineering ─────────────────────────────────────────────────────

def _regressed_avg(all_scores, recent_n=5):
    """Blend season average with recent games via Bayesian shrinkage."""
    prior_weight = MLB_EV_CONFIG["regressed_prior_weight"]
    default = MLB_EV_CONFIG["league_avg_runs"]
    if not all_scores:
        return default
    season_avg = sum(all_scores) / len(all_scores)
    recent = all_scores[-recent_n:] if len(all_scores) >= recent_n else all_scores
    recent_avg = sum(recent) / len(recent)
    n = len(all_scores)
    return (n * season_avg + prior_weight * recent_avg) / (n + prior_weight)


def _spread_to_implied(spread):
    """
    Convert a spread to approximate moneyline implied probability.
    Fallback for games where moneyline is unavailable.
    MLB spread of -1.5 roughly corresponds to ~60% implied.
    """
    if spread is None:
        return 0.5
    return 0.5 + abs(spread) * 0.05


def _extract_features(game, team_state):
    """
    Extract feature vector for one MLB game.

    Returns:
        dict of feature_name -> value, or None if insufficient data
    """
    closing = game.get("closing_spread")
    opening = game.get("opening_spread")
    over_under = game.get("over_under")
    moneyline = game.get("moneyline")

    # Need either moneyline or spread to identify dog/fav
    if closing is None and moneyline is None:
        return None

    # Dog/fav identification
    # For MLB: negative moneyline = favorite, positive = underdog
    # If using spread: negative = home favored
    if moneyline is not None:
        if moneyline < 0:
            # Home is favorite
            fav_team = game["home_team"]
            dog_team = game["away_team"]
        else:
            fav_team = game["away_team"]
            dog_team = game["home_team"]
    elif closing is not None:
        if closing < 0:
            fav_team = game["home_team"]
            dog_team = game["away_team"]
        else:
            fav_team = game["away_team"]
            dog_team = game["home_team"]
    else:
        return None

    fav_st = team_state.get(fav_team)
    dog_st = team_state.get(dog_team)

    if not fav_st or not dog_st:
        return None
    if len(fav_st.get("scores", [])) < 5 or len(dog_st.get("scores", [])) < 5:
        return None

    # Feature 1: moneyline_implied — convert ML odds to implied probability
    if moneyline is not None:
        if moneyline < 0:
            moneyline_implied = abs(moneyline) / (abs(moneyline) + 100.0)
        elif moneyline > 0:
            moneyline_implied = 100.0 / (moneyline + 100.0)
        else:
            moneyline_implied = 0.5
    elif closing is not None:
        # Fallback: use spread as proxy
        moneyline_implied = _spread_to_implied(closing)
    else:
        moneyline_implied = 0.5

    # Feature 2: clv — closing line value (dog perspective)
    if opening is not None and closing is not None:
        clv = closing - opening
        if closing > 0:
            clv = -clv
    else:
        clv = 0.0

    # Feature 3: line_movement_abs
    line_movement_abs = abs(closing - opening) if (opening is not None and closing is not None) else 0.0

    # Feature 4-5: regressed runs for/against (offensive efficiency)
    dog_runs_regressed = _regressed_avg(dog_st["scores"])
    fav_runs_regressed = _regressed_avg(fav_st["scores"])

    # Feature 6: run_diff_net — (dog_RF - dog_RA) - (fav_RF - fav_RA)
    dog_ra = _regressed_avg(dog_st.get("opp_scores", []))
    fav_ra = _regressed_avg(fav_st.get("opp_scores", []))
    dog_net = dog_runs_regressed - dog_ra
    fav_net = fav_runs_regressed - fav_ra
    run_diff_net = dog_net - fav_net

    # Feature 7: total (over/under — pace proxy)
    total = over_under if over_under is not None else MLB_EV_CONFIG["default_total"]

    # Feature 8: elo_diff (Elo rating difference, dog - fav)
    from constants import USE_ELO_FEATURES
    if USE_ELO_FEATURES:
        try:
            from power_ratings import get_elo
            dog_elo = get_elo(dog_team, "mlb")
            fav_elo = get_elo(fav_team, "mlb")
            elo_diff = (dog_elo - fav_elo) / 100.0
        except Exception:
            elo_diff = 0.0
    else:
        elo_diff = 0.0

    # Feature 9: home_away — 1 if dog is home, 0 if away
    home_away = 1.0 if dog_team == game.get("home_team") else 0.0

    return {
        "moneyline_implied": moneyline_implied,
        "clv": clv,
        "line_movement_abs": line_movement_abs,
        "dog_runs_regressed": dog_runs_regressed,
        "fav_runs_regressed": fav_runs_regressed,
        "run_diff_net": run_diff_net,
        "total": total,
        "elo_diff": elo_diff,
        "home_away": home_away,
    }


# ─── Dataset Builder ─────────────────────────────────────────────────────────

def build_mlb_ev_dataset():
    """
    Build chronological dataset from tm_historical_games for MLB.

    Returns:
        list of (features_dict, target) tuples sorted chronologically.
        target: 1 if underdog won outright, 0 if not.
    """
    from test_model import db as tm_db

    games = tm_db.get_historical_games("mlb")
    if not games:
        return []

    # MLB target: dog won outright (moneyline outcome)
    # Need final scores and spread/moneyline to identify dog
    eligible = [
        g for g in games
        if g.get("game_status") == "STATUS_FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
        and (g.get("closing_spread") is not None or g.get("moneyline") is not None)
    ]

    eligible.sort(key=lambda g: g.get("game_date", ""))

    warmup = MLB_EV_CONFIG["warmup_games"]
    window = MLB_EV_CONFIG["rolling_window"]

    team_state = {}
    dataset = []

    for i, game in enumerate(eligible):
        home = game["home_team"]
        away = game["away_team"]

        for t in (home, away):
            if t not in team_state:
                team_state[t] = {
                    "scores": [], "opp_scores": [], "results": [], "dates": [],
                }

        if i >= warmup:
            features = _extract_features(game, team_state)
            if features is not None:
                closing = game.get("closing_spread")
                moneyline = game.get("moneyline")
                home_score = game["home_score"]
                away_score = game["away_score"]

                # Determine target: did the underdog win outright?
                if moneyline is not None:
                    if moneyline < 0:
                        # Home favored → dog is away
                        target = 1 if away_score > home_score else 0
                    else:
                        # Away favored → dog is home
                        target = 1 if home_score > away_score else 0
                elif closing is not None:
                    if closing < 0:
                        # Home favored → dog is away
                        target = 1 if away_score > home_score else 0
                    else:
                        # Away favored → dog is home
                        target = 1 if home_score > away_score else 0
                else:
                    continue

                dataset.append((features, target))

        _update_team_state(game, team_state, window)

    return dataset


def _update_team_state(game, team_state, window):
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

    for t in (home, away):
        for key in ("scores", "opp_scores", "results", "dates"):
            if len(team_state[t][key]) > window:
                team_state[t][key] = team_state[t][key][-window:]


# ─── Training (Walk-Forward Rolling Only) ────────────────────────────────────

def train_mlb_ev_model(dataset):
    """
    Train via strict walk-forward rolling validation.
    After rolling validation, trains a final model on ALL data for deployment.

    Returns:
        dict with validation metrics, final model params, edge buckets
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, brier_score_loss

    if len(dataset) < 100:
        return {"error": f"Insufficient data: {len(dataset)} games (need 100+)"}

    feature_names = MLB_EV_CONFIG["feature_names"]
    C = MLB_EV_CONFIG["regularization_C"]
    train_size = MLB_EV_CONFIG["rolling_train_size"]
    test_size = MLB_EV_CONFIG["rolling_test_size"]
    step = MLB_EV_CONFIG["rolling_step"]

    X = np.array([[d[0][f] for f in feature_names] for d in dataset], dtype=float)
    y = np.array([d[1] for d in dataset], dtype=float)

    # ── Phase 1: Walk-forward rolling validation ──
    fold_aucs = []
    fold_accuracies = []
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
        all_y_prob.extend(y_prob.tolist())
        all_y_true.extend(y_test.tolist())

        i += step

    if not fold_aucs:
        return {"error": "No valid folds in rolling validation"}

    mean_auc = float(np.mean(fold_aucs))
    std_auc = float(np.std(fold_aucs))
    mean_acc = float(np.mean(fold_accuracies))

    # Edge bucket analysis on all OOS predictions
    all_y_prob_arr = np.array(all_y_prob)
    all_y_true_arr = np.array(all_y_true)
    edge_buckets = _compute_edge_buckets(all_y_prob_arr, all_y_true_arr)
    monotonic = _check_monotonicity(edge_buckets)

    # OOS accuracy and ROI
    oos_wins = int(np.sum(all_y_true_arr))
    oos_total = len(all_y_true_arr)
    oos_accuracy = round(oos_wins / oos_total * 100, 2) if oos_total > 0 else 0

    # OOS ROI for bets with edge >= 3%
    implied = MLB_EV_CONFIG["implied_prob"]
    oos_edges = all_y_prob_arr - implied
    ev_mask = oos_edges >= 0.03
    ev_count = int(np.sum(ev_mask))
    if ev_count > 0:
        ev_wins = int(np.sum(all_y_true_arr[ev_mask]))
        ev_losses = ev_count - ev_wins
        ev_roi = round(((ev_wins * (100 / 110) - ev_losses) / ev_count) * 100, 2)
        ev_accuracy = round(ev_wins / ev_count * 100, 2)
    else:
        ev_roi = 0.0
        ev_accuracy = 0.0

    # ECE on OOS predictions
    ece = _compute_ece(all_y_prob_arr, all_y_true_arr)

    # AUC gate
    auc_gate = MLB_EV_CONFIG["auc_gate"]
    is_valid = mean_auc >= auc_gate

    # ── Phase 2: Train final model on all data (for deployment) ──
    final_scaler = StandardScaler()
    X_all_s = final_scaler.fit_transform(X)

    final_model = LogisticRegression(
        penalty="l2", C=C, solver="lbfgs", max_iter=1000, random_state=42,
    )
    final_model.fit(X_all_s, y)

    coefficients = {}
    for j, name in enumerate(feature_names):
        coefficients[name] = round(float(final_model.coef_[0][j]), 4)
    coefficients["intercept"] = round(float(final_model.intercept_[0]), 4)

    # Brier score on OOS
    brier = float(brier_score_loss(all_y_true_arr, all_y_prob_arr))

    # Isotonic calibration if ECE > 5%
    isotonic_params = None
    if ece > 5.0 and is_valid:
        isotonic_params = _fit_isotonic(all_y_prob_arr, all_y_true_arr)

    result = {
        "mode": "walkforward_rolling",
        "is_valid": is_valid,
        "mean_auc": round(mean_auc, 4),
        "std_auc": round(std_auc, 4),
        "auc_gate": auc_gate,
        "mean_accuracy": round(mean_acc, 2),
        "n_folds": len(fold_aucs),
        "fold_aucs": [round(a, 4) for a in fold_aucs],
        "oos_predictions": oos_total,
        "oos_accuracy": oos_accuracy,
        "brier_score": round(brier, 4),
        "ece": round(ece, 2),
        "edge_buckets": edge_buckets,
        "monotonicity_pass": monotonic,
        "ev_bets": ev_count,
        "ev_accuracy": ev_accuracy,
        "ev_roi": ev_roi,
        "coefficients": coefficients,
        "scaler_mean": final_scaler.mean_.tolist(),
        "scaler_std": final_scaler.scale_.tolist(),
        "feature_names": feature_names,
        "isotonic_params": isotonic_params,
        "base_rate": round(float(np.mean(y)) * 100, 2),
    }

    if is_valid:
        _load_model_to_cache(result)

    return result


# ─── Edge Bucket Analysis ────────────────────────────────────────────────────

def _compute_edge_buckets(y_prob, y_actual):
    """Compute ROI and accuracy per edge bucket."""
    implied = MLB_EV_CONFIG["implied_prob"]
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
        return True
    for i in range(1, len(populated)):
        if populated[i]["roi"] < populated[i - 1]["roi"]:
            return False
    return True


# ─── ECE and Isotonic Calibration ────────────────────────────────────────────

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


def _fit_isotonic(y_prob, y_actual):
    """Fit isotonic regression for post-hoc calibration."""
    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        return None

    if len(y_prob) < 50:
        return None

    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    iso.fit(y_prob, y_actual)

    if hasattr(iso, "X_thresholds_") and hasattr(iso, "y_thresholds_"):
        x_bp = iso.X_thresholds_.tolist()
        y_bp = iso.y_thresholds_.tolist()
    else:
        x_lin = np.linspace(float(y_prob.min()), float(y_prob.max()), 50)
        y_lin = iso.predict(x_lin)
        x_bp = x_lin.tolist()
        y_bp = y_lin.tolist()

    return {
        "x": [round(v, 6) for v in x_bp],
        "y": [round(v, 6) for v in y_bp],
    }


def _apply_isotonic(prob, iso_params):
    """Apply isotonic calibration to a raw probability."""
    if iso_params is None:
        return prob
    calibrated = float(np.interp(prob, iso_params["x"], iso_params["y"]))
    return calibrated


# ─── EV Computation ──────────────────────────────────────────────────────────

def compute_ev(model_prob):
    """
    Compute edge and EV per unit at -110 odds.

    Returns:
        (edge, ev_per_unit) tuple
    """
    implied = MLB_EV_CONFIG["implied_prob"]
    edge = model_prob - implied
    ev_per_unit = model_prob * (100 / 110) - (1 - model_prob)
    return round(edge, 4), round(ev_per_unit, 4)


def get_ev_recommendation(model_prob):
    """Map model probability to recommendation tier based on edge."""
    edge = model_prob - MLB_EV_CONFIG["implied_prob"]
    tiers = MLB_EV_CONFIG["edge_tiers"]
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
    global _mlb_ev_cache
    _mlb_ev_cache = {
        "model": None,
        "scaler_mean": result["scaler_mean"],
        "scaler_std": result["scaler_std"],
        "feature_names": result["feature_names"],
        "auc": result.get("mean_auc"),
        "is_valid": result["is_valid"],
        "isotonic": result.get("isotonic_params"),
        "coefficients": result["coefficients"],
    }
    print(f"[mlb_ev] Model loaded — AUC: {result.get('mean_auc')}, "
          f"valid: {result['is_valid']}, monotonic: {result['monotonicity_pass']}",
          flush=True)


def load_mlb_ev_model(model_params):
    """
    Load a previously saved MLB EV model from model_params dict.
    Called at app startup from tm_model_runs.
    """
    global _mlb_ev_cache

    auc = model_params.get("mean_auc") or model_params.get("auc", 0)
    is_valid = auc >= MLB_EV_CONFIG["auc_gate"]

    _mlb_ev_cache = {
        "model": None,
        "scaler_mean": model_params.get("scaler_mean", []),
        "scaler_std": model_params.get("scaler_std", []),
        "feature_names": model_params.get("feature_names", MLB_EV_CONFIG["feature_names"]),
        "auc": auc,
        "is_valid": is_valid,
        "isotonic": model_params.get("isotonic_params"),
        "coefficients": model_params.get("coefficients", {}),
    }
    if is_valid:
        print(f"[mlb_ev] Model restored from DB — AUC: {auc}", flush=True)
    else:
        print(f"[mlb_ev] Model loaded but below AUC gate ({auc} < {MLB_EV_CONFIG['auc_gate']})", flush=True)


def is_ev_model_active():
    """Check if MLB EV model is loaded and valid."""
    return _mlb_ev_cache.get("is_valid", False)


def predict_single(features_dict):
    """
    Predict underdog win probability for a single MLB game.

    Returns:
        dict with probability, edge, ev, recommendation, or None if inactive
    """
    if not is_ev_model_active():
        return None

    cache = _mlb_ev_cache
    feature_names = cache["feature_names"]
    coefs = cache["coefficients"]
    scaler_mean = cache["scaler_mean"]
    scaler_std = cache["scaler_std"]

    if not coefs or not scaler_mean or not scaler_std:
        return None
    if len(scaler_mean) != len(feature_names):
        return None

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

    # Apply isotonic calibration if available
    if cache.get("isotonic"):
        prob = _apply_isotonic(prob, cache["isotonic"])

    edge, ev_per_unit = compute_ev(prob)
    recommendation = get_ev_recommendation(prob)

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

_live_team_state = {}
_live_state_loaded = False


def load_live_team_state():
    """Populate team_state from historical DB for live feature extraction."""
    global _live_team_state, _live_state_loaded
    try:
        from test_model import db as tm_db
        games = tm_db.get_historical_games("mlb")
        if not games:
            return

        eligible = [
            g for g in games
            if g.get("game_status") == "STATUS_FINAL"
            and g.get("home_score") is not None
        ]
        eligible.sort(key=lambda g: g.get("game_date", ""))

        team_state = {}
        window = MLB_EV_CONFIG["rolling_window"]
        for game in eligible:
            _update_team_state(game, team_state, window)

        _live_team_state = team_state
        _live_state_loaded = True
        print(f"[mlb_ev] Live team state loaded: {len(team_state)} teams", flush=True)
    except Exception as e:
        print(f"[mlb_ev] Failed to load live team state: {e}", flush=True)


def extract_live_features(current_spread, opening_spread, over_under,
                          home_team, away_team, game_date_str):
    """
    Extract features for a live game using cached team state.

    Returns:
        features_dict or None
    """
    if not _live_state_loaded:
        return None

    game = {
        "closing_spread": current_spread,
        "opening_spread": opening_spread,
        "over_under": over_under,
        "home_team": home_team,
        "away_team": away_team,
        "game_date": game_date_str,
        "moneyline": None,  # Falls back to spread-based dog/fav identification
    }

    return _extract_features(game, _live_team_state)


# ─── Full Training Pipeline ──────────────────────────────────────────────────

def run_full_training():
    """
    Full training pipeline: build dataset -> walk-forward validate -> save.
    Runs synchronously.
    """
    from test_model import db as tm_db

    with _ev_lock:
        _ev_progress.update({
            "status": "building_dataset",
            "message": "Building MLB feature dataset from historical games...",
        })

    dataset = build_mlb_ev_dataset()
    if not dataset:
        with _ev_lock:
            _ev_progress.update({
                "status": "error",
                "message": "No dataset could be built. Collect more MLB historical data.",
            })
        return

    with _ev_lock:
        _ev_progress.update({
            "status": "training",
            "message": f"Walk-forward validation on {len(dataset)} games...",
            "dataset_size": len(dataset),
        })

    result = train_mlb_ev_model(dataset)
    if "error" in result:
        with _ev_lock:
            _ev_progress.update({
                "status": "error",
                "message": result["error"],
            })
        return

    with _ev_lock:
        _ev_progress.update({
            "status": "saving",
            "message": "Saving model results...",
        })

    tm_db.save_model_run({
        "sport": "mlb",
        "run_type": "ev_logistic",
        "accuracy": result.get("mean_accuracy"),
        "roi": result.get("ev_roi"),
        "total_predictions": result.get("oos_predictions", 0),
        "qualified_bets": result.get("ev_bets", 0),
        "model_params": {
            "mean_auc": result["mean_auc"],
            "std_auc": result["std_auc"],
            "brier_score": result.get("brier_score"),
            "coefficients": result["coefficients"],
            "scaler_mean": result["scaler_mean"],
            "scaler_std": result["scaler_std"],
            "feature_names": result["feature_names"],
            "edge_buckets": result["edge_buckets"],
            "monotonicity_pass": result["monotonicity_pass"],
            "ece": result.get("ece"),
            "isotonic_params": result.get("isotonic_params"),
            "is_valid": result["is_valid"],
            "ev_roi": result.get("ev_roi"),
            "ev_accuracy": result.get("ev_accuracy"),
            "ev_bets": result.get("ev_bets"),
            "fold_aucs": result.get("fold_aucs"),
        },
        "feature_importances": result["coefficients"],
        "threshold_analysis": {
            "edge_buckets": result["edge_buckets"],
        },
    })

    if result["is_valid"]:
        load_live_team_state()

    with _ev_lock:
        _ev_progress.update({
            "status": "complete",
            "message": "Training complete.",
            "result": result,
        })

    return result


def start_ev_training_thread():
    """Start MLB EV training in a background thread."""
    with _ev_lock:
        if _ev_progress.get("status") in ("running", "building_dataset", "training", "saving"):
            return False
        _ev_progress.update({"status": "running", "message": "Starting..."})

    t = threading.Thread(target=run_full_training, daemon=True)
    t.start()
    return True
