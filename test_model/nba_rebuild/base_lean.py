"""
Phase 2: Validate Base Lean

Answers: Does "always lean underdog" actually work for NBA?

Tests:
1. Overall dog cover rate + Wilson 95% CI
2. By-slot cover rates (public vs vegas)
3. Slot split: does slot type matter (>= 4% gap)?
4. Bare walk-forward: 500-train/100-test with score=0, prediction=underdog
   — this is the FLOOR for any model
"""

import threading
from datetime import datetime, timedelta

from constants import wilson_interval, metric_with_ci, proportion_z_test
from test_model import db as tm_db
from time_slots import classify_slot

# ─── Progress tracking ────────────────────────────────────────────────────

_progress = {}
_lock = threading.Lock()


def get_base_lean_status():
    with _lock:
        return dict(_progress)


def start_base_lean_thread():
    with _lock:
        if _progress.get("status") == "running":
            return False
        _progress.clear()
        _progress["status"] = "running"

    t = threading.Thread(target=_run_base_lean, daemon=True)
    t.start()
    return True


def _run_base_lean():
    try:
        result = analyze_base_lean()
        with _lock:
            _progress["status"] = "complete"
            _progress["result"] = result
    except Exception as e:
        with _lock:
            _progress["status"] = "error"
            _progress["error"] = str(e)


# ─── Core Analysis ────────────────────────────────────────────────────────

def analyze_base_lean():
    """
    Returns:
    - overall_dog_cover_rate + Wilson 95% CI
    - by_slot: {public: {rate, ci, n}, vegas: {rate, ci, n}}
    - slot_split: abs(public_rate - vegas_rate)
    - slot_matters: bool (True if split >= 4%)
    - bare_walkforward: walk-forward with 500-train/100-test,
      lean=underdog, score=0 for all. Reports accuracy + CI per fold,
      aggregated accuracy. This is the FLOOR.
    """
    games = tm_db.get_historical_games("nba")

    # Filter eligible games
    eligible = []
    for g in games:
        if g.get("game_status") != "STATUS_FINAL":
            continue
        if g.get("closing_spread") is None:
            continue
        if g.get("home_covered") not in (0, 1):
            continue
        eligible.append(g)

    eligible.sort(key=lambda g: g.get("game_date", ""))

    if not eligible:
        return {"error": "No eligible games found", "total_eligible": 0}

    # Classify slots for each game
    _classify_games(eligible)

    # 1. Overall dog cover rate
    dog_covers = 0
    for g in eligible:
        # Negative spread = home favored, dog = away
        # home_covered=0 means home did NOT cover → dog covered
        spread = g["closing_spread"]
        home_covered = g["home_covered"]
        if spread < 0:
            # Home favored, dog=away. Dog covers when home_covered=0
            if home_covered == 0:
                dog_covers += 1
        elif spread > 0:
            # Away favored, dog=home. Dog covers when home_covered=1
            if home_covered == 1:
                dog_covers += 1
        # spread == 0: pick'em, skip

    total = len(eligible)
    overall_rate = round(dog_covers / total * 100, 2) if total > 0 else 0
    overall_ci = wilson_interval(dog_covers, total)
    overall_z, overall_p = proportion_z_test(dog_covers, total, 0.50)

    # 2. By-slot cover rates
    by_slot = {}
    for slot in ("public", "vegas", "unknown"):
        slot_games = [g for g in eligible if g.get("_slot_type") == slot]
        if not slot_games:
            continue
        slot_dogs = 0
        for g in slot_games:
            spread = g["closing_spread"]
            hc = g["home_covered"]
            if spread < 0 and hc == 0:
                slot_dogs += 1
            elif spread > 0 and hc == 1:
                slot_dogs += 1
        n = len(slot_games)
        rate = round(slot_dogs / n * 100, 2) if n > 0 else 0
        ci = wilson_interval(slot_dogs, n)
        by_slot[slot] = {"rate": rate, "ci_lower": ci[0], "ci_upper": ci[1], "n": n,
                         "wins": slot_dogs}

    # 3. Slot split
    pub_rate = by_slot.get("public", {}).get("rate", 0)
    veg_rate = by_slot.get("vegas", {}).get("rate", 0)
    slot_split = round(abs(pub_rate - veg_rate), 2)
    slot_matters = slot_split >= 4.0

    # 4. Bare walk-forward
    walkforward = _bare_walkforward(eligible, train_size=500, test_size=100, step=100)

    # Save results
    try:
        tm_db.save_model_run({
            "sport": "nba",
            "run_type": "nba_base_lean",
            "accuracy": overall_rate,
            "total_predictions": total,
            "model_params": {
                "overall_rate": overall_rate,
                "overall_ci": list(overall_ci),
                "overall_p": overall_p,
                "by_slot": by_slot,
                "slot_split": slot_split,
                "slot_matters": slot_matters,
                "walkforward": walkforward,
            },
        })
    except Exception:
        pass

    return {
        "total_eligible": total,
        "overall_dog_cover_rate": overall_rate,
        "overall_ci": {"lower": overall_ci[0], "upper": overall_ci[1]},
        "overall_z": overall_z,
        "overall_p": overall_p,
        "by_slot": by_slot,
        "slot_split": slot_split,
        "slot_matters": slot_matters,
        "walkforward": walkforward,
    }


def _classify_games(games):
    """Add _slot_type to each game dict by parsing game_date."""
    for g in games:
        gd = g.get("game_date", "")
        if not gd:
            g["_slot_type"] = "unknown"
            continue
        try:
            game_dt = datetime.fromisoformat(gd.replace("Z", "+00:00"))
            # NBA uses PST (UTC-8) for classification
            pst_dt = game_dt - timedelta(hours=8)
            hour, minute = pst_dt.hour, pst_dt.minute
            day_of_week = pst_dt.strftime("%A")
            slot_type = classify_slot(day_of_week, hour, minute)
            g["_slot_type"] = slot_type
        except (ValueError, TypeError):
            g["_slot_type"] = "unknown"


def _bare_walkforward(games, train_size=500, test_size=100, step=100):
    """
    Walk-forward with bare underdog lean (score=0).
    Each fold: train on N games (just to advance the window), test on next M.
    Prediction = always underdog.
    """
    n = len(games)
    folds = []
    total_correct = 0
    total_tested = 0

    start = 0
    while start + train_size + test_size <= n:
        test_start = start + train_size
        test_end = test_start + test_size
        test_games = games[test_start:test_end]

        correct = 0
        for g in test_games:
            spread = g["closing_spread"]
            hc = g["home_covered"]
            # Always predict underdog
            if spread < 0 and hc == 0:
                correct += 1
            elif spread > 0 and hc == 1:
                correct += 1

        fold_n = len(test_games)
        fold_acc = round(correct / fold_n * 100, 2) if fold_n > 0 else 0
        fold_ci = wilson_interval(correct, fold_n)
        folds.append({
            "fold": len(folds) + 1,
            "test_start": test_start,
            "test_end": test_end,
            "accuracy": fold_acc,
            "ci_lower": fold_ci[0],
            "ci_upper": fold_ci[1],
            "n": fold_n,
            "correct": correct,
        })

        total_correct += correct
        total_tested += fold_n
        start += step

    agg_acc = round(total_correct / total_tested * 100, 2) if total_tested > 0 else 0
    agg_ci = wilson_interval(total_correct, total_tested)

    return {
        "folds": folds,
        "aggregate_accuracy": agg_acc,
        "aggregate_ci": {"lower": agg_ci[0], "upper": agg_ci[1]},
        "total_tested": total_tested,
        "total_correct": total_correct,
        "num_folds": len(folds),
    }
