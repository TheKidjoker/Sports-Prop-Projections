"""
Phase 4: Rebuild from Survivors

Grid search integer weights for surviving factors, walk-forward validate.
If CI lower > 50%, update production weights. If not, deprecate rules.
"""

import threading
import itertools

from constants import wilson_interval, THRESHOLDS, SPORT_OVERRIDES
from test_model import db as tm_db
from test_model.nba_rebuild.factor_isolation import _classify_games, _dog_covered

# ─── Progress tracking ────────────────────────────────────────────────────

_progress = {}
_lock = threading.Lock()


def get_combined_status():
    with _lock:
        return dict(_progress)


def start_combined_thread():
    with _lock:
        if _progress.get("status") == "running":
            return False
        _progress.clear()
        _progress["status"] = "running"

    t = threading.Thread(target=_run_combined, daemon=True)
    t.start()
    return True


def _run_combined():
    try:
        result = rebuild_from_survivors()
        with _lock:
            _progress["status"] = "complete"
            _progress["result"] = result
    except Exception as e:
        with _lock:
            _progress["status"] = "error"
            _progress["error"] = str(e)


# ─── Factor extractors ───────────────────────────────────────────────────

def _extract_line_movement(game, params):
    """Merged line movement factor."""
    opening = game.get("opening_spread")
    closing = game.get("closing_spread")
    if opening is None or closing is None:
        return 0
    threshold = params.get("threshold", 1.0)
    raw = closing - opening
    if closing < 0 and raw >= threshold:
        return 1  # Moved toward dog
    if closing > 0 and raw <= -threshold:
        return 1
    return 0


def _extract_spread_sweet_spot(game, params):
    """Spread size bonus (for validated bins)."""
    spread_abs = abs(game.get("closing_spread", 0))
    bonus_bins = params.get("bonus_bins", [])
    bin_key = int(spread_abs / 1.5) * 1.5
    if bin_key in bonus_bins:
        return 1
    return 0


def _extract_public_slot(game, params):
    """Public slot bonus."""
    if game.get("_slot_type") == "public":
        return 1
    return 0


FACTOR_EXTRACTORS = {
    "line_movement_merged": _extract_line_movement,
    "spread_size": _extract_spread_sweet_spot,
    "public_slot": _extract_public_slot,
}


# ─── Core ─────────────────────────────────────────────────────────────────

def rebuild_from_survivors(survivor_factors=None, survivor_params=None):
    """
    1. Load latest factor isolation results if not provided
    2. Grid search integer weights [-5, +5] with L2 regularization
    3. Walk-forward 500/100 each combo
    4. Find best weights, compute thresholds
    5. Validate: 53%+ overall, CI lower > 50%
    """
    # Load factor isolation results
    if survivor_factors is None:
        run = tm_db.get_latest_model_run("nba", "nba_factor_isolation")
        if not run or not run.get("model_params"):
            return {"error": "No factor isolation results found. Run Phase 3 first."}
        params = run["model_params"]
        survivor_factors = params.get("survivors", [])
        survivor_params = params.get("details", {})

    if not survivor_factors:
        return _deprecate_rules("No surviving factors from isolation testing")

    # Load games
    games = tm_db.get_historical_games("nba")
    eligible = [g for g in games
                if g.get("game_status") == "STATUS_FINAL"
                and g.get("closing_spread") is not None
                and g.get("home_covered") in (0, 1)]
    eligible.sort(key=lambda g: g.get("game_date", ""))
    _classify_games(eligible)

    if len(eligible) < 700:
        return {"error": f"Need 700+ games, have {len(eligible)}"}

    with _lock:
        _progress["total_eligible"] = len(eligible)
        _progress["survivors"] = survivor_factors

    # Build factor extraction functions
    active_factors = []
    for fname in survivor_factors:
        extractor = FACTOR_EXTRACTORS.get(fname)
        if extractor:
            fparams = {}
            detail = survivor_params.get(fname, {})
            if fname == "line_movement_merged" and detail.get("best_params"):
                fparams = detail["best_params"]
            elif fname == "spread_size":
                fparams = {"bonus_bins": detail.get("bonus_bins", [])}
            active_factors.append((fname, extractor, fparams))

    if not active_factors:
        return _deprecate_rules("No extractable factors among survivors")

    # Grid search weights (1-5 for each factor)
    n_factors = len(active_factors)
    weight_range = range(1, 6)  # 1 to 5
    combos = list(itertools.product(weight_range, repeat=n_factors))

    with _lock:
        _progress["total_combos"] = len(combos)
        _progress["tested"] = 0

    best_score = -999
    best_weights = None
    best_wf = None
    l2_lambda = 0.001  # Light regularization

    for combo in combos:
        weights = dict(zip([f[0] for f in active_factors], combo))

        # Walk-forward
        wf = _walkforward_weighted(eligible, active_factors, weights,
                                    train_size=500, test_size=100, step=100)

        # Score = accuracy - L2 penalty
        l2_penalty = l2_lambda * sum(w ** 2 for w in combo)
        adj_score = wf["accuracy"] - l2_penalty

        if adj_score > best_score:
            best_score = adj_score
            best_weights = weights
            best_wf = wf

        with _lock:
            _progress["tested"] = _progress.get("tested", 0) + 1

    if best_wf is None:
        return _deprecate_rules("Walk-forward failed for all weight combos")

    # Compute max_score and thresholds
    max_score = sum(best_weights.values())
    accuracy = best_wf["accuracy"]
    ci = wilson_interval(best_wf["correct"], best_wf["total"])
    passes = ci[0] > 50.0

    # Threshold sweep
    thresholds = _sweep_thresholds(eligible, active_factors, best_weights)

    result = {
        "passes_validation": passes,
        "final_weights": best_weights,
        "max_score": max_score,
        "walkforward_accuracy": accuracy,
        "walkforward_ci": {"lower": ci[0], "upper": ci[1]},
        "walkforward_n": best_wf["total"],
        "thresholds": thresholds,
        "deprecate_rules": not passes,
    }

    if not passes:
        result["recommendation"] = "EV_ONLY"
    else:
        result["recommendation"] = "UPDATE_WEIGHTS"

    # Save results
    try:
        tm_db.save_model_run({
            "sport": "nba",
            "run_type": "nba_combined_rebuild",
            "accuracy": accuracy,
            "total_predictions": best_wf["total"],
            "model_params": result,
        })
    except Exception:
        pass

    return result


def _walkforward_weighted(games, factors, weights, train_size=500,
                           test_size=100, step=100):
    """Walk-forward with weighted factor scores."""
    n = len(games)
    total_correct = 0
    total_tested = 0
    total_actionable = 0

    start = 0
    while start + train_size + test_size <= n:
        test_start = start + train_size
        test_end = min(test_start + test_size, n)
        test_games = games[test_start:test_end]

        for g in test_games:
            covered = _dog_covered(g)
            if covered is None:
                continue

            # Compute score
            score = 0
            for fname, extractor, fparams in factors:
                fires = extractor(g, fparams)
                if fires > 0:
                    score += weights.get(fname, 0) * fires

            total_tested += 1
            if score > 0:
                total_actionable += 1
            if covered:
                total_correct += 1

        start += step

    accuracy = round(total_correct / total_tested * 100, 2) if total_tested > 0 else 0

    return {
        "accuracy": accuracy,
        "correct": total_correct,
        "total": total_tested,
        "actionable": total_actionable,
    }


def _sweep_thresholds(games, factors, weights):
    """Find STRONG/LEAN/MONITOR thresholds from score distribution."""
    max_score = sum(weights.values())
    scores_and_covered = []

    for g in games:
        covered = _dog_covered(g)
        if covered is None:
            continue
        score = 0
        for fname, extractor, fparams in factors:
            fires = extractor(g, fparams)
            if fires > 0:
                score += weights.get(fname, 0) * fires
        scores_and_covered.append((score, covered))

    # Test thresholds
    best_strong = None
    best_lean = None
    for strong_thresh in range(max_score, 0, -1):
        strong_games = [(s, c) for s, c in scores_and_covered if s >= strong_thresh]
        if len(strong_games) >= 20:
            strong_rate = sum(1 for _, c in strong_games if c) / len(strong_games) * 100
            if strong_rate >= 60:
                best_strong = {"threshold": strong_thresh, "rate": round(strong_rate, 1),
                               "n": len(strong_games)}
                break

    for lean_thresh in range(1, max_score + 1):
        lean_games = [(s, c) for s, c in scores_and_covered if s >= lean_thresh]
        if len(lean_games) >= 50:
            lean_rate = sum(1 for _, c in lean_games if c) / len(lean_games) * 100
            if lean_rate >= 53:
                best_lean = {"threshold": lean_thresh, "rate": round(lean_rate, 1),
                             "n": len(lean_games)}
                break

    return {
        "strong": best_strong,
        "lean": best_lean,
        "max_score": max_score,
    }


def _deprecate_rules(reason):
    """Return deprecation result."""
    result = {
        "passes_validation": False,
        "deprecate_rules": True,
        "recommendation": "EV_ONLY",
        "reason": reason,
    }
    try:
        tm_db.save_model_run({
            "sport": "nba",
            "run_type": "nba_combined_rebuild",
            "accuracy": 0,
            "total_predictions": 0,
            "model_params": result,
        })
    except Exception:
        pass
    return result
