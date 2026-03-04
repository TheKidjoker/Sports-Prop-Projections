"""
Slot Validation — statistically tests whether time slot classification
(public vs vegas) produces meaningfully different dog cover rates.

Uses three tests:
  1. Per-slot z-test vs 50% baseline
  2. Chi-squared test across all slots
  3. Permutation test (1000 iterations) for slot-cover-rate differences
"""

import random
import threading
from collections import defaultdict
from datetime import datetime, timezone

from time_slots import classify_slot
from constants import proportion_z_test, wilson_interval
from test_model import db as tm_db
from test_model.date_utils import parse_game_dt

# Progress dict for polling
_sv_progress = {}
_sv_lock = threading.Lock()


def get_slot_validation_status(sport):
    with _sv_lock:
        return dict(_sv_progress.get(sport, {}))


def start_slot_validation_thread(sport):
    """Start slot validation in a background thread. Returns immediately."""
    with _sv_lock:
        existing = _sv_progress.get(sport, {})
        if existing.get("status") == "running":
            return False

    t = threading.Thread(target=run_slot_validation, args=(sport,), daemon=True)
    t.start()
    return True


def _group_games_by_date(games):
    """Group games by calendar date string for slate context."""
    by_date = defaultdict(list)
    for game in games:
        gd = game.get("game_date", "")
        date_key = gd[:10] if gd else "unknown"
        by_date[date_key].append(game)
    for dk in by_date:
        by_date[dk].sort(key=lambda g: g.get("game_date", ""))
    return by_date


def run_slot_validation(sport):
    """
    Validate the time slot hypothesis for a sport.
    Tests whether public vs vegas slots produce different dog cover rates.
    """
    with _sv_lock:
        _sv_progress[sport] = {"status": "running", "progress": 0, "message": "Loading data..."}

    try:
        games = tm_db.get_historical_games(sport)
        if not games:
            with _sv_lock:
                _sv_progress[sport] = {"status": "error", "message": "No historical data"}
            return

        # Filter to final games with closing_spread and home_covered
        eligible = [
            g for g in games
            if g.get("game_status") == "STATUS_FINAL"
            and g.get("closing_spread") is not None
            and g.get("home_covered") in (0, 1)
        ]

        if len(eligible) < 50:
            with _sv_lock:
                _sv_progress[sport] = {
                    "status": "error",
                    "message": f"Insufficient data: {len(eligible)} games (need 50+)",
                }
            return

        with _sv_lock:
            _sv_progress[sport]["message"] = f"Classifying {len(eligible)} games..."
            _sv_progress[sport]["progress"] = 10

        # Group by date for slate context
        games_by_date = _group_games_by_date(eligible)

        # Classify each game's slot and determine dog cover
        slot_outcomes = defaultdict(lambda: {"covers": 0, "total": 0})
        classified = 0

        for date_key, day_games in games_by_date.items():
            total_on_date = len(day_games)
            for game_idx, game in enumerate(day_games):
                game_date_str = game.get("game_date", "")
                local_dt = parse_game_dt(game_date_str, sport)
                if local_dt is None:
                    continue

                hour = local_dt.hour
                minute = local_dt.minute
                day_of_week = local_dt.strftime("%A")

                # Classify slot (sport-specific args)
                if sport == "nhl":
                    slot_type = classify_slot(
                        day_of_week, hour, minute,
                        sport="nhl",
                        total_games_on_slate=total_on_date,
                        game_index=game_idx,
                    )
                elif sport in ("cfb", "cbb"):
                    slot_type = classify_slot(day_of_week, hour, minute, sport=sport)
                elif sport == "nfl":
                    slot_type = classify_slot(day_of_week, hour, minute, sport="nfl")
                else:
                    slot_type = classify_slot(day_of_week, hour, minute)

                if slot_type in ("unknown", "skip"):
                    continue

                # Determine dog cover
                closing_spread = game["closing_spread"]
                home_covered = game["home_covered"]

                # Dog covers when: home is dog (spread > 0) and home covers,
                # or away is dog (spread < 0) and away covers (home doesn't)
                if closing_spread > 0:
                    dog_covered = home_covered == 1
                elif closing_spread < 0:
                    dog_covered = home_covered == 0
                else:
                    continue  # pick'em, skip

                slot_outcomes[slot_type]["total"] += 1
                if dog_covered:
                    slot_outcomes[slot_type]["covers"] += 1
                classified += 1

        with _sv_lock:
            _sv_progress[sport]["progress"] = 60
            _sv_progress[sport]["message"] = f"Running statistical tests on {classified} classified games..."

        # ── Per-slot z-test vs 50% baseline ──
        per_slot = {}
        for slot_type, data in slot_outcomes.items():
            covers = data["covers"]
            total = data["total"]
            if total == 0:
                continue
            rate = round(covers / total * 100, 2)
            z_stat, p_value = proportion_z_test(covers, total, baseline=0.50)
            ci_lower, ci_upper = wilson_interval(covers, total)
            per_slot[slot_type] = {
                "dog_cover_rate": rate,
                "total_games": total,
                "covers": covers,
                "z_stat": z_stat,
                "p_value": p_value,
                "significant": p_value < 0.05,
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
            }

        # ── Chi-squared test across all slots ──
        chi_squared_result = _chi_squared_test(slot_outcomes)

        with _sv_lock:
            _sv_progress[sport]["progress"] = 80
            _sv_progress[sport]["message"] = "Running permutation test..."

        # ── Permutation test ──
        permutation_result = _permutation_test(slot_outcomes, n_iter=1000)

        with _sv_lock:
            _sv_progress[sport]["progress"] = 95
            _sv_progress[sport]["message"] = "Saving results..."

        # Save results
        results = {
            "per_slot": per_slot,
            "chi_squared": chi_squared_result,
            "permutation_test": permutation_result,
            "total_games": classified,
            "total_eligible": len(eligible),
        }

        tm_db.save_model_run({
            "sport": sport,
            "run_type": "slot_validation",
            "accuracy": None,
            "roi": None,
            "total_predictions": classified,
            "model_params": results,
        })

        with _sv_lock:
            _sv_progress[sport] = {
                "status": "complete",
                "progress": 100,
                "message": "Done",
                "metrics": results,
            }

    except Exception as e:
        with _sv_lock:
            _sv_progress[sport] = {"status": "error", "message": str(e)}


def _chi_squared_test(slot_outcomes):
    """Chi-squared independence test: are slot type and cover outcome independent?"""
    try:
        from scipy.stats import chi2_contingency
    except ImportError:
        return {"statistic": None, "p_value": None, "significant": False,
                "error": "scipy not available"}

    slots = [(k, v) for k, v in slot_outcomes.items() if v["total"] >= 10]
    if len(slots) < 2:
        return {"statistic": None, "p_value": None, "significant": False,
                "error": "Need at least 2 slots with 10+ games"}

    # Contingency table: rows = slots, cols = [covers, non-covers]
    table = [[v["covers"], v["total"] - v["covers"]] for _, v in slots]

    stat, p, dof, _ = chi2_contingency(table)
    return {
        "statistic": round(float(stat), 4),
        "p_value": round(float(p), 6),
        "significant": p < 0.05,
        "degrees_of_freedom": int(dof),
        "slots_tested": [k for k, _ in slots],
    }


def _permutation_test(slot_outcomes, n_iter=1000):
    """
    Permutation test: shuffle slot labels and measure if the observed
    spread of cover rates exceeds random chance.
    """
    slots = [(k, v) for k, v in slot_outcomes.items() if v["total"] >= 10]
    if len(slots) < 2:
        return {"actual_diff": None, "p_value": None, "significant": False}

    # Observed: max cover rate difference between any two slots
    rates = [v["covers"] / v["total"] for _, v in slots]
    actual_diff = max(rates) - min(rates)

    # Build flat arrays for permutation
    all_outcomes = []  # (covered: bool, slot_index: int)
    slot_sizes = []
    for i, (_, v) in enumerate(slots):
        slot_sizes.append(v["total"])
        all_outcomes.extend([True] * v["covers"] + [False] * (v["total"] - v["covers"]))

    random.seed(42)
    exceed_count = 0

    for _ in range(n_iter):
        random.shuffle(all_outcomes)
        # Assign shuffled outcomes to slot groups
        idx = 0
        perm_rates = []
        for size in slot_sizes:
            chunk = all_outcomes[idx:idx + size]
            perm_rates.append(sum(chunk) / size if size else 0)
            idx += size
        perm_diff = max(perm_rates) - min(perm_rates)
        if perm_diff >= actual_diff:
            exceed_count += 1

    p_value = exceed_count / n_iter
    return {
        "actual_diff": round(actual_diff * 100, 2),
        "p_value": round(p_value, 4),
        "significant": p_value < 0.05,
        "n_iterations": n_iter,
    }
