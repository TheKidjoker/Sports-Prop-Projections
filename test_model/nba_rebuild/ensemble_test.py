"""
Phase 5C: Ensemble Testing

Test two ensemble approaches combining rules + EV predictions:
1. Simple average: 0.5 * rules_prob + 0.5 * ev_prob
2. Rules score as additional feature in EV logistic regression

Walk-forward both. Compare vs EV-only and rules-only.
"""

import threading
import numpy as np

from constants import EV_CONFIG, wilson_interval
from test_model import db as tm_db
from test_model.nba_rebuild.factor_isolation import _classify_games, _dog_covered

# ─── Progress tracking ────────────────────────────────────────────────────

_progress = {}
_lock = threading.Lock()


def get_ensemble_status():
    with _lock:
        return dict(_progress)


def start_ensemble_thread():
    with _lock:
        if _progress.get("status") == "running":
            return False
        _progress.clear()
        _progress["status"] = "running"

    t = threading.Thread(target=_run_ensemble, daemon=True)
    t.start()
    return True


def _run_ensemble():
    try:
        result = test_ensemble()
        with _lock:
            _progress["status"] = "complete"
            _progress["result"] = result
    except Exception as e:
        with _lock:
            _progress["status"] = "error"
            _progress["error"] = str(e)


# ─── Core ─────────────────────────────────────────────────────────────────

def test_ensemble():
    """
    Build aligned datasets of (rules_score, ev_prob, target) and test:
    1. EV-only: walk-forward accuracy using EV model probability
    2. Rules-only: walk-forward accuracy using rules score > threshold
    3. Simple average: 0.5 * calibrated_rules_prob + 0.5 * ev_prob
    4. Stacked: rules_score as extra feature in EV logistic regression

    Returns comparison metrics for all four approaches.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import roc_auc_score, brier_score_loss
    from nba_ev_model import build_nba_ev_dataset, _extract_features, _regressed_avg

    # Build EV dataset
    ev_dataset = build_nba_ev_dataset()
    if len(ev_dataset) < 700:
        return {"error": f"Need 700+ EV observations, have {len(ev_dataset)}"}

    feature_names = EV_CONFIG["feature_names"]

    # Build arrays
    X_ev = np.array([[d[0][f] for f in feature_names] for d in ev_dataset], dtype=float)
    y = np.array([d[1] for d in ev_dataset], dtype=float)

    # Build rules scores from historical games (aligned with EV dataset)
    games = tm_db.get_historical_games("nba")
    eligible = [g for g in games
                if g.get("game_status") == "STATUS_FINAL"
                and g.get("closing_spread") is not None
                and g.get("home_covered") in (0, 1)]
    eligible.sort(key=lambda g: g.get("game_date", ""))
    _classify_games(eligible)

    # Build a simple rules score from slot + line movement
    rules_scores = []
    for g in eligible:
        score = 0
        slot = g.get("_slot_type", "unknown")
        if slot == "public":
            score += 2  # public_slot_bonus
        opening = g.get("opening_spread")
        closing = g.get("closing_spread")
        if opening is not None and closing is not None:
            raw = closing - opening
            if closing < 0 and raw >= 1.0:
                score += 2  # line moved toward dog
            elif closing > 0 and raw <= -1.0:
                score += 2
        rules_scores.append(score)

    # Align: EV dataset starts at warmup offset, rules covers all eligible
    warmup = EV_CONFIG["warmup_games"]
    if len(eligible) < len(ev_dataset) + warmup:
        # Can't align perfectly — use what we have
        aligned_rules = rules_scores[warmup:warmup + len(ev_dataset)]
    else:
        aligned_rules = rules_scores[warmup:warmup + len(ev_dataset)]

    # Trim to match
    min_len = min(len(ev_dataset), len(aligned_rules))
    X_ev = X_ev[:min_len]
    y = y[:min_len]
    aligned_rules = aligned_rules[:min_len]
    rules_arr = np.array(aligned_rules, dtype=float).reshape(-1, 1)

    # Walk-forward parameters
    train_size = 500
    test_size = 100
    step = 100
    C = EV_CONFIG["regularization_C"]

    # Results accumulators
    results = {
        "ev_only": {"correct": 0, "total": 0, "probs": [], "actuals": []},
        "rules_only": {"correct": 0, "total": 0},
        "simple_avg": {"correct": 0, "total": 0, "probs": [], "actuals": []},
        "stacked": {"correct": 0, "total": 0, "probs": [], "actuals": []},
    }

    with _lock:
        n_folds = max(0, (min_len - train_size - test_size) // step + 1)
        _progress["total_folds"] = n_folds
        _progress["tested_folds"] = 0

    i = 0
    while i + train_size + test_size <= min_len:
        # Split data
        X_ev_train = X_ev[i:i + train_size]
        y_train = y[i:i + train_size]
        X_ev_test = X_ev[i + train_size:i + train_size + test_size]
        y_test = y[i + train_size:i + train_size + test_size]
        rules_train = rules_arr[i:i + train_size]
        rules_test = rules_arr[i + train_size:i + train_size + test_size]

        # 1. EV-only model
        scaler_ev = StandardScaler()
        X_ev_train_s = scaler_ev.fit_transform(X_ev_train)
        X_ev_test_s = scaler_ev.transform(X_ev_test)

        model_ev = LogisticRegression(
            penalty="l2", C=C, solver="lbfgs", max_iter=1000, random_state=42,
        )
        model_ev.fit(X_ev_train_s, y_train)
        ev_probs = model_ev.predict_proba(X_ev_test_s)[:, 1]
        ev_preds = (ev_probs >= 0.5).astype(int)
        results["ev_only"]["correct"] += int(np.sum(ev_preds == y_test))
        results["ev_only"]["total"] += len(y_test)
        results["ev_only"]["probs"].extend(ev_probs.tolist())
        results["ev_only"]["actuals"].extend(y_test.tolist())

        # 2. Rules-only (score > 0 → predict dog covers)
        rules_preds = (rules_test.flatten() > 0).astype(int)
        results["rules_only"]["correct"] += int(np.sum(rules_preds == y_test))
        results["rules_only"]["total"] += len(y_test)

        # 3. Simple average — convert rules score to rough probability
        max_rules = 4  # max possible from slot + line_movement
        rules_probs = np.clip(0.5 + rules_test.flatten() / (2 * max(max_rules, 1)), 0.3, 0.7)
        avg_probs = 0.5 * ev_probs + 0.5 * rules_probs
        avg_preds = (avg_probs >= 0.5).astype(int)
        results["simple_avg"]["correct"] += int(np.sum(avg_preds == y_test))
        results["simple_avg"]["total"] += len(y_test)
        results["simple_avg"]["probs"].extend(avg_probs.tolist())
        results["simple_avg"]["actuals"].extend(y_test.tolist())

        # 4. Stacked: rules_score as extra feature in EV model
        X_stacked_train = np.hstack([X_ev_train, rules_train])
        X_stacked_test = np.hstack([X_ev_test, rules_test])
        scaler_stacked = StandardScaler()
        X_stacked_train_s = scaler_stacked.fit_transform(X_stacked_train)
        X_stacked_test_s = scaler_stacked.transform(X_stacked_test)

        model_stacked = LogisticRegression(
            penalty="l2", C=C, solver="lbfgs", max_iter=1000, random_state=42,
        )
        model_stacked.fit(X_stacked_train_s, y_train)
        stacked_probs = model_stacked.predict_proba(X_stacked_test_s)[:, 1]
        stacked_preds = (stacked_probs >= 0.5).astype(int)
        results["stacked"]["correct"] += int(np.sum(stacked_preds == y_test))
        results["stacked"]["total"] += len(y_test)
        results["stacked"]["probs"].extend(stacked_probs.tolist())
        results["stacked"]["actuals"].extend(y_test.tolist())

        i += step
        with _lock:
            _progress["tested_folds"] = _progress.get("tested_folds", 0) + 1

    # Compute final metrics
    output = {"dataset_size": min_len}
    for name, acc in results.items():
        total = acc["total"]
        correct = acc["correct"]
        if total == 0:
            output[name] = {"accuracy": 0, "n": 0}
            continue

        accuracy = round(correct / total * 100, 2)
        ci = wilson_interval(correct, total)
        entry = {
            "accuracy": accuracy,
            "ci_lower": ci[0],
            "ci_upper": ci[1],
            "n": total,
        }

        # Add AUC + Brier for methods with probabilities
        if acc.get("probs"):
            probs_arr = np.array(acc["probs"])
            actuals_arr = np.array(acc["actuals"])
            try:
                entry["auc"] = round(roc_auc_score(actuals_arr, probs_arr), 4)
            except ValueError:
                entry["auc"] = None
            entry["brier"] = round(brier_score_loss(actuals_arr, probs_arr), 4)

        output[name] = entry

    # Determine best approach
    approaches = [(name, output[name]["accuracy"]) for name in
                  ("ev_only", "rules_only", "simple_avg", "stacked")
                  if output.get(name, {}).get("accuracy", 0) > 0]
    approaches.sort(key=lambda x: x[1], reverse=True)
    output["best_approach"] = approaches[0][0] if approaches else "unknown"

    # Save
    try:
        tm_db.save_model_run({
            "sport": "nba",
            "run_type": "nba_ensemble_test",
            "accuracy": output.get(output["best_approach"], {}).get("accuracy", 0),
            "total_predictions": min_len,
            "model_params": output,
        })
    except Exception:
        pass

    return output
