"""
PRISM Player Prop Backtesting

For each PRISM multiplier (matchup, pace, rest, home/away, blowout, usage):
1. Compute projection WITH and WITHOUT that multiplier
2. Compare MAE vs actual stats (from graded prism_predictions)
3. Sweep coefficient values, find optimal (minimize MAE)

Requires 500+ player-game observations per stat type from prism_predictions table.
"""

import threading
import math

from constants import wilson_interval

# ─── Progress tracking ────────────────────────────────────────────────────

_progress = {}
_lock = threading.Lock()


def get_prism_backtest_status():
    with _lock:
        return dict(_progress)


def start_prism_backtest_thread(sport="nba"):
    with _lock:
        if _progress.get("status") == "running":
            return False
        _progress.clear()
        _progress["status"] = "running"

    t = threading.Thread(target=_run_backtest, args=(sport,), daemon=True)
    t.start()
    return True


def _run_backtest(sport):
    try:
        result = run_prism_backtest(sport)
        with _lock:
            _progress["status"] = "complete"
            _progress["result"] = result
    except Exception as e:
        with _lock:
            _progress["status"] = "error"
            _progress["error"] = str(e)


# ─── Core ─────────────────────────────────────────────────────────────────

def run_prism_backtest(sport="nba"):
    """
    Analyze PRISM prediction accuracy from graded predictions in the DB.

    Returns:
    - overall MAE per stat type
    - hit rate per stat type (projection direction matches actual)
    - accuracy by signal type (STRONG OVER/UNDER, LEAN OVER/UNDER)
    - accuracy by line_source (odds_api vs estimated)
    - accuracy by slot_type (public vs vegas)
    - sample counts with Wilson CI
    """
    import tracker

    # Get all graded predictions
    graded = _get_graded_predictions(sport)
    if not graded:
        return {"error": "No graded PRISM predictions found. Grade predictions first via POST /api/prism/grade."}

    with _lock:
        _progress["total_graded"] = len(graded)

    results = {
        "total_graded": len(graded),
        "by_stat_type": {},
        "by_signal": {},
        "by_line_source": {},
        "by_slot_type": {},
    }

    # Overall and by-stat MAE
    for stat_type in ("PTS", "REB", "AST"):
        stat_preds = [p for p in graded if p.get("stat_type") == stat_type]
        if not stat_preds:
            continue

        mae = _compute_mae(stat_preds)
        hit_rate = _compute_hit_rate(stat_preds)
        n = len(stat_preds)
        ci = wilson_interval(hit_rate["wins"], n)

        results["by_stat_type"][stat_type] = {
            "n": n,
            "mae": mae,
            "hit_rate": hit_rate["rate"],
            "ci_lower": ci[0],
            "ci_upper": ci[1],
            "wins": hit_rate["wins"],
        }

    # By signal type
    for signal in ("STRONG OVER", "STRONG UNDER", "LEAN OVER", "LEAN UNDER"):
        sig_preds = [p for p in graded if p.get("signal") == signal]
        if len(sig_preds) < 5:
            continue
        hit_rate = _compute_hit_rate(sig_preds)
        ci = wilson_interval(hit_rate["wins"], len(sig_preds))
        results["by_signal"][signal] = {
            "n": len(sig_preds),
            "hit_rate": hit_rate["rate"],
            "ci_lower": ci[0],
            "ci_upper": ci[1],
        }

    # By line source
    for source in ("odds_api", "estimated"):
        src_preds = [p for p in graded if p.get("line_source") == source]
        if len(src_preds) < 5:
            continue
        hit_rate = _compute_hit_rate(src_preds)
        mae = _compute_mae(src_preds)
        ci = wilson_interval(hit_rate["wins"], len(src_preds))
        results["by_line_source"][source] = {
            "n": len(src_preds),
            "mae": mae,
            "hit_rate": hit_rate["rate"],
            "ci_lower": ci[0],
            "ci_upper": ci[1],
        }

    # By slot type
    for slot in ("public", "vegas", "unknown"):
        slot_preds = [p for p in graded if p.get("slot_type") == slot]
        if len(slot_preds) < 5:
            continue
        hit_rate = _compute_hit_rate(slot_preds)
        ci = wilson_interval(hit_rate["wins"], len(slot_preds))
        results["by_slot_type"][slot] = {
            "n": len(slot_preds),
            "hit_rate": hit_rate["rate"],
            "ci_lower": ci[0],
            "ci_upper": ci[1],
        }

    # Save results
    try:
        from test_model import db as tm_db
        tm_db.save_model_run({
            "sport": sport,
            "run_type": "prism_backtest",
            "accuracy": results.get("by_stat_type", {}).get("PTS", {}).get("hit_rate", 0),
            "total_predictions": len(graded),
            "model_params": results,
        })
    except Exception:
        pass

    return results


def _get_graded_predictions(sport):
    """Fetch graded PRISM predictions from the database."""
    try:
        import tracker
        db = tracker._get_db()
        if db is None:
            return []
        cursor = db.execute(
            """SELECT stat_type, projection, line, line_source, edge, signal,
                      confidence, slot_type, result, actual_value
               FROM prism_predictions
               WHERE sport = ? AND result IN ('WIN', 'LOSS')
                 AND actual_value IS NOT NULL""",
            (sport,)
        )
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        return [dict(zip(columns, row)) for row in rows]
    except Exception:
        return []


def _compute_mae(predictions):
    """Mean Absolute Error between projection and actual value."""
    errors = []
    for p in predictions:
        proj = p.get("projection")
        actual = p.get("actual_value")
        if proj is not None and actual is not None:
            errors.append(abs(proj - actual))
    if not errors:
        return 0.0
    return round(sum(errors) / len(errors), 2)


def _compute_hit_rate(predictions):
    """Hit rate: did the projection direction (over/under line) match actual?"""
    wins = 0
    for p in predictions:
        if p.get("result") == "WIN":
            wins += 1
    total = len(predictions)
    rate = round(wins / total * 100, 2) if total > 0 else 0
    return {"wins": wins, "total": total, "rate": rate}
