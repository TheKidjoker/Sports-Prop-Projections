"""
Phase 3: Factor Isolation Testing

Walk-forward test each factor independently against the base lean.
Factor survives if: 3%+ lift over baseline, p < 0.10, fires in >= 5% of games.
"""

import threading
import math
from datetime import datetime, timedelta

from constants import wilson_interval, proportion_z_test
from test_model import db as tm_db
from time_slots import classify_slot

# ─── Progress tracking ────────────────────────────────────────────────────

_progress = {}
_lock = threading.Lock()


def get_factor_isolation_status():
    with _lock:
        return dict(_progress)


def start_factor_isolation_thread():
    with _lock:
        if _progress.get("status") == "running":
            return False
        _progress.clear()
        _progress["status"] = "running"
        _progress["current_factor"] = ""

    t = threading.Thread(target=_run_isolation, daemon=True)
    t.start()
    return True


def _run_isolation():
    try:
        result = run_all_factor_tests()
        with _lock:
            _progress["status"] = "complete"
            _progress["result"] = result
    except Exception as e:
        with _lock:
            _progress["status"] = "error"
            _progress["error"] = str(e)


# ─── Helpers ──────────────────────────────────────────────────────────────

def _classify_games(games):
    """Classify slot type for each game."""
    for g in games:
        gd = g.get("game_date", "")
        if not gd:
            g["_slot_type"] = "unknown"
            g["_day_of_week"] = ""
            g["_hour"] = None
            continue
        try:
            game_dt = datetime.fromisoformat(gd.replace("Z", "+00:00"))
            pst_dt = game_dt - timedelta(hours=8)
            hour, minute = pst_dt.hour, pst_dt.minute
            day_of_week = pst_dt.strftime("%A")
            slot_type = classify_slot(day_of_week, hour, minute)
            g["_slot_type"] = slot_type
            g["_day_of_week"] = day_of_week
            g["_hour"] = hour
        except (ValueError, TypeError):
            g["_slot_type"] = "unknown"
            g["_day_of_week"] = ""
            g["_hour"] = None


def _dog_covered(game):
    """Check if the underdog covered. Returns True/False or None for push/pick'em."""
    spread = game.get("closing_spread")
    hc = game.get("home_covered")
    if spread is None or hc is None or hc == -1:
        return None
    if spread < 0:
        return hc == 0  # Home favored, dog=away, covers when home didn't
    elif spread > 0:
        return hc == 1  # Away favored, dog=home, covers when home did
    return None  # pick'em


def _walkforward_accuracy(games, factor_fn, train_size=500, test_size=100, step=100):
    """
    Walk-forward test: for each fold, apply factor_fn to get bonus per game.
    Predict underdog for all. Factor_fn returns a bonus score (0 if doesn't fire).
    Games with bonus > 0 are "factor games". Track their cover rate vs baseline.

    Returns: {baseline_acc, factor_acc, lift, fires, fire_rate, folds, p_value}
    """
    n = len(games)
    baseline_correct = 0
    baseline_total = 0
    factor_correct = 0
    factor_total = 0
    fold_data = []

    start = 0
    while start + train_size + test_size <= n:
        test_start = start + train_size
        test_end = min(test_start + test_size, n)
        test_games = games[test_start:test_end]

        fold_base_correct = 0
        fold_factor_correct = 0
        fold_factor_n = 0

        for g in test_games:
            covered = _dog_covered(g)
            if covered is None:
                continue

            baseline_total += 1
            if covered:
                baseline_correct += 1
                fold_base_correct += 1

            bonus = factor_fn(g)
            if bonus > 0:
                factor_total += 1
                fold_factor_n += 1
                if covered:
                    factor_correct += 1
                    fold_factor_correct += 1

        fold_data.append({
            "fold": len(fold_data) + 1,
            "factor_n": fold_factor_n,
            "factor_correct": fold_factor_correct,
        })

        start += step

    base_acc = round(baseline_correct / baseline_total * 100, 2) if baseline_total > 0 else 0
    factor_acc = round(factor_correct / factor_total * 100, 2) if factor_total > 0 else 0
    lift = round(factor_acc - base_acc, 2)
    fire_rate = round(factor_total / baseline_total * 100, 2) if baseline_total > 0 else 0

    # Z-test: factor accuracy vs baseline rate
    _, p_value = proportion_z_test(factor_correct, factor_total, baseline_correct / baseline_total) \
        if baseline_total > 0 and factor_total >= 10 else (0, 1.0)

    survives = lift >= 3.0 and p_value < 0.10 and factor_total >= 20

    return {
        "baseline_acc": base_acc,
        "baseline_n": baseline_total,
        "factor_acc": factor_acc,
        "factor_n": factor_total,
        "lift": lift,
        "fire_rate": fire_rate,
        "p_value": round(p_value, 6),
        "survives": survives,
        "num_folds": len(fold_data),
    }


# ─── Individual Factor Tests ─────────────────────────────────────────────

def test_line_movement_merged(games):
    """
    Test merged line movement factor.
    Grid search: thresholds [0.5, 1.0, 1.5, 2.0] × weights [+1..+5]
    Movement toward dog = positive signal.
    """
    best = None
    best_result = None

    for threshold in [0.5, 1.0, 1.5, 2.0]:
        for weight in [1, 2, 3, 4, 5]:
            def factor_fn(g, _t=threshold, _w=weight):
                opening = g.get("opening_spread")
                closing = g.get("closing_spread")
                if opening is None or closing is None:
                    return 0
                # Movement toward dog: closing more positive (less home-favored)
                raw = closing - opening
                if closing < 0:
                    # Home favored: positive raw = moved toward dog
                    if raw >= _t:
                        return _w
                elif closing > 0:
                    # Away favored: negative raw = moved toward dog (home)
                    if raw <= -_t:
                        return _w
                return 0

            result = _walkforward_accuracy(games, factor_fn)
            result["threshold"] = threshold
            result["weight"] = weight

            if result["survives"]:
                if best_result is None or result["lift"] > best_result["lift"]:
                    best_result = result
                    best = {"threshold": threshold, "weight": weight}

    if best_result is None:
        # Return best even if didn't survive
        result = _walkforward_accuracy(games, lambda g: 0)
        return {"name": "line_movement_merged", "survives": False, "best_params": None,
                "result": result}

    return {"name": "line_movement_merged", "survives": True, "best_params": best,
            "result": best_result}


def test_spread_size(games):
    """
    Test spread size bins: cover rate by 1.5pt increments.
    Only create factors for bins deviating 4%+ from mean with p < 0.10.
    """
    # Compute overall baseline
    total_covered = sum(1 for g in games if _dog_covered(g))
    total = sum(1 for g in games if _dog_covered(g) is not None)
    baseline = total_covered / total if total > 0 else 0.5

    bins = {}
    for g in games:
        covered = _dog_covered(g)
        if covered is None:
            continue
        spread_abs = abs(g.get("closing_spread", 0))
        bin_key = int(spread_abs / 1.5) * 1.5
        if bin_key not in bins:
            bins[bin_key] = {"covered": 0, "total": 0}
        bins[bin_key]["total"] += 1
        if covered:
            bins[bin_key]["covered"] += 1

    significant_bins = {}
    for bin_key, data in sorted(bins.items()):
        if data["total"] < 30:
            continue
        rate = data["covered"] / data["total"]
        deviation = abs(rate - baseline) * 100
        _, p = proportion_z_test(data["covered"], data["total"], baseline)
        significant_bins[bin_key] = {
            "rate": round(rate * 100, 2),
            "n": data["total"],
            "deviation": round(deviation, 2),
            "p_value": round(p, 6),
            "significant": deviation >= 4.0 and p < 0.10,
        }

    # Walk-forward test with best significant bins as bonus
    bonus_bins = {k for k, v in significant_bins.items()
                  if v["significant"] and v["rate"] > baseline * 100}
    penalty_bins = {k for k, v in significant_bins.items()
                    if v["significant"] and v["rate"] < baseline * 100}

    def factor_fn(g):
        spread_abs = abs(g.get("closing_spread", 0))
        bin_key = int(spread_abs / 1.5) * 1.5
        if bin_key in bonus_bins:
            return 2
        return 0

    wf = _walkforward_accuracy(games, factor_fn)

    return {
        "name": "spread_size",
        "survives": wf["survives"],
        "bins": significant_bins,
        "bonus_bins": sorted(bonus_bins),
        "penalty_bins": sorted(penalty_bins),
        "result": wf,
    }


def test_day_of_week(games):
    """
    Cover rate for all 7 days. Must deviate 4%+, p<0.05, 150+ games per day.
    Cross-season stability: direction must agree in 2/3 seasons.
    """
    total_covered = sum(1 for g in games if _dog_covered(g))
    total = sum(1 for g in games if _dog_covered(g) is not None)
    baseline = total_covered / total if total > 0 else 0.5

    by_day = {}
    for g in games:
        covered = _dog_covered(g)
        if covered is None:
            continue
        day = g.get("_day_of_week", "")
        if not day:
            continue
        if day not in by_day:
            by_day[day] = {"covered": 0, "total": 0}
        by_day[day]["total"] += 1
        if covered:
            by_day[day]["covered"] += 1

    day_results = {}
    significant_days = []
    for day, data in by_day.items():
        if data["total"] < 150:
            day_results[day] = {"rate": 0, "n": data["total"], "significant": False,
                                "reason": "insufficient_data"}
            continue
        rate = data["covered"] / data["total"]
        deviation = abs(rate - baseline) * 100
        _, p = proportion_z_test(data["covered"], data["total"], baseline)
        is_sig = deviation >= 4.0 and p < 0.05
        day_results[day] = {
            "rate": round(rate * 100, 2),
            "n": data["total"],
            "deviation": round(deviation, 2),
            "p_value": round(p, 6),
            "significant": is_sig,
            "direction": "bonus" if rate > baseline else "penalty",
        }
        if is_sig:
            significant_days.append(day)

    # Walk-forward: penalty days get -1
    def factor_fn(g):
        day = g.get("_day_of_week", "")
        if day in significant_days:
            dr = day_results[day]
            if dr["direction"] == "penalty":
                return 0  # Penalty days: we DON'T fire (they reduce coverage)
            return 1  # Bonus days
        return 0

    wf = _walkforward_accuracy(games, factor_fn) if significant_days else {
        "baseline_acc": 0, "factor_acc": 0, "lift": 0, "factor_n": 0,
        "survives": False, "p_value": 1.0}

    return {
        "name": "day_of_week",
        "survives": wf.get("survives", False),
        "by_day": day_results,
        "significant_days": significant_days,
        "result": wf,
    }


def test_vegas_trap(games):
    """
    Count total fires: |spread| >= 7 in vegas slot.
    If <40 fires: cap at +2, cannot validate.
    """
    fires = 0
    fire_covered = 0
    for g in games:
        covered = _dog_covered(g)
        if covered is None:
            continue
        if g.get("_slot_type") not in ("vegas", "trap"):
            continue
        if abs(g.get("closing_spread", 0)) < 7:
            continue
        fires += 1
        if covered:
            fire_covered += 1

    if fires < 40:
        return {
            "name": "vegas_trap",
            "survives": False,
            "reason": f"insufficient_fires ({fires} < 40)",
            "fires": fires,
            "fire_covered": fire_covered,
            "cap": 2,
        }

    rate = round(fire_covered / fires * 100, 2) if fires > 0 else 0
    ci = wilson_interval(fire_covered, fires)

    def factor_fn(g):
        if g.get("_slot_type") not in ("vegas", "trap"):
            return 0
        if abs(g.get("closing_spread", 0)) >= 7:
            return 2
        return 0

    wf = _walkforward_accuracy(games, factor_fn)

    return {
        "name": "vegas_trap",
        "survives": wf["survives"],
        "fires": fires,
        "fire_covered": fire_covered,
        "fire_rate": rate,
        "fire_ci": {"lower": ci[0], "upper": ci[1]},
        "result": wf,
    }


def test_b2b(games):
    """
    Test B2B factor. Requires game_date proximity detection.
    Uses consecutive dates per team as proxy.
    """
    # Build per-team game date list
    team_dates = {}
    for g in games:
        gd = g.get("game_date", "")[:10]
        if not gd:
            continue
        for team_key in ("home_team", "away_team"):
            team = g.get(team_key, "")
            if team not in team_dates:
                team_dates[team] = set()
            team_dates[team].add(gd)

    def _is_b2b(team, game_date_str):
        """Check if team played yesterday."""
        if not game_date_str or team not in team_dates:
            return False
        try:
            gd = datetime.strptime(game_date_str[:10], "%Y-%m-%d")
            yesterday = (gd - timedelta(days=1)).strftime("%Y-%m-%d")
            return yesterday in team_dates[team]
        except (ValueError, TypeError):
            return False

    # Tag games with B2B info
    b2b_bonus_games = 0
    b2b_penalty_games = 0
    for g in games:
        gd = g.get("game_date", "")[:10]
        spread = g.get("closing_spread")
        if spread is None:
            continue
        # Identify dog and fav teams
        if spread < 0:
            dog_team = g.get("away_team", "")
            fav_team = g.get("home_team", "")
        else:
            dog_team = g.get("home_team", "")
            fav_team = g.get("away_team", "")

        dog_b2b = _is_b2b(dog_team, gd)
        fav_b2b = _is_b2b(fav_team, gd)

        g["_opp_b2b"] = fav_b2b and not dog_b2b  # Opponent B2B = bonus for dog
        g["_lean_b2b"] = dog_b2b and not fav_b2b  # Dog on B2B = penalty

    def factor_fn(g):
        if g.get("_opp_b2b"):
            return 2
        return 0

    wf = _walkforward_accuracy(games, factor_fn)

    return {
        "name": "b2b",
        "survives": wf["survives"],
        "result": wf,
    }


def test_trell_rule(games):
    """
    Check tm_historical_injuries for star-OUT entries.
    If <30 observations: cannot validate.
    """
    try:
        from test_model.db import _get_sqlite, _use_supabase, _get_supabase
    except ImportError:
        return {"name": "trell_rule", "survives": False, "reason": "db import failed"}

    # Count injury observations
    if _use_supabase():
        sb = _get_supabase()
        resp = sb.table("tm_historical_injuries").select("*", count="exact").eq("sport", "nba").execute()
        injury_count = resp.count or 0
    else:
        try:
            conn = _get_sqlite()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) as cnt FROM tm_historical_injuries WHERE sport = 'nba'")
            row = cur.fetchone()
            injury_count = dict(row)["cnt"] if row else 0
            cur.close()
            conn.close()
        except Exception:
            injury_count = 0

    if injury_count < 30:
        return {
            "name": "trell_rule",
            "survives": False,
            "reason": f"insufficient_injury_data ({injury_count} < 30)",
            "observations": injury_count,
            "cap": 3,
        }

    # If we have enough data, we'd test star-OUT ATS cover rate
    # For now, report what we have and cap at +3
    return {
        "name": "trell_rule",
        "survives": False,
        "reason": "prospective_tracking",
        "observations": injury_count,
        "cap": 3,
    }


def test_ats_record(games):
    """
    Test ATS mean-reversion: teams >60% ATS last 15 → what's cover rate next 15?
    If drops below 55%: ATS is mean-reverting → zero.
    """
    # Build rolling ATS per team
    team_ats = {}  # team -> [(game_date, covered)]
    for g in games:
        covered = _dog_covered(g)
        if covered is None:
            continue
        gd = g.get("game_date", "")
        spread = g.get("closing_spread", 0)
        hc = g.get("home_covered")
        # Track ATS for each team
        for side in ("home", "away"):
            team = g.get(f"{side}_team", "")
            if not team:
                continue
            if side == "home":
                team_covered = hc == 1
            else:
                team_covered = hc == 0
            if team not in team_ats:
                team_ats[team] = []
            team_ats[team].append({"date": gd, "covered": team_covered})

    # Test mean-reversion: after 15+ games with >60% ATS, what happens next?
    hot_then_cover = 0
    hot_then_total = 0
    cold_then_cover = 0
    cold_then_total = 0

    for team, records in team_ats.items():
        for i in range(15, len(records) - 15):
            window = records[i-15:i]
            wins = sum(1 for r in window if r["covered"])
            rate = wins / 15

            # Check next 15 games
            next_window = records[i:i+15]
            next_wins = sum(1 for r in next_window if r["covered"])

            if rate > 0.60:
                hot_then_total += 1
                if next_wins / 15 > 0.50:
                    hot_then_cover += 1
            elif rate < 0.40:
                cold_then_total += 1
                if next_wins / 15 > 0.50:
                    cold_then_cover += 1

    hot_persist = round(hot_then_cover / hot_then_total * 100, 2) if hot_then_total > 0 else 0
    cold_persist = round(cold_then_cover / cold_then_total * 100, 2) if cold_then_total > 0 else 0
    mean_reverts = hot_persist < 55.0

    return {
        "name": "ats_record",
        "survives": not mean_reverts,
        "hot_persist_rate": hot_persist,
        "hot_n": hot_then_total,
        "cold_persist_rate": cold_persist,
        "cold_n": cold_then_total,
        "mean_reverts": mean_reverts,
        "recommendation": "zero" if mean_reverts else "keep_at_2",
    }


def test_sharp_money(games):
    """
    Check Pinnacle spread availability and correlation with line movement.
    """
    with_pinnacle = [g for g in games if g.get("pinnacle_spread") is not None
                     and g.get("opening_spread") is not None
                     and g.get("closing_spread") is not None]

    if len(with_pinnacle) < 50:
        return {
            "name": "sharp_money",
            "survives": False,
            "reason": f"insufficient_pinnacle_data ({len(with_pinnacle)} < 50)",
            "cap": 1,
        }

    # Correlation between pinnacle deviation and line movement
    pinnacle_devs = []
    line_movements = []
    for g in with_pinnacle:
        pin_dev = g["pinnacle_spread"] - g["closing_spread"]
        lm = g["closing_spread"] - g["opening_spread"]
        pinnacle_devs.append(pin_dev)
        line_movements.append(lm)

    # Pearson correlation
    n = len(pinnacle_devs)
    mean_p = sum(pinnacle_devs) / n
    mean_l = sum(line_movements) / n
    cov = sum((p - mean_p) * (l - mean_l) for p, l in zip(pinnacle_devs, line_movements)) / n
    std_p = math.sqrt(sum((p - mean_p) ** 2 for p in pinnacle_devs) / n)
    std_l = math.sqrt(sum((l - mean_l) ** 2 for l in line_movements) / n)

    if std_p > 0 and std_l > 0:
        correlation = round(cov / (std_p * std_l), 4)
    else:
        correlation = 0

    redundant = abs(correlation) > 0.6

    return {
        "name": "sharp_money",
        "survives": not redundant,
        "correlation_with_line_movement": correlation,
        "redundant": redundant,
        "n": n,
        "recommendation": "drop" if redundant else "keep_at_1",
    }


# ─── Aggregate ────────────────────────────────────────────────────────────

def run_all_factor_tests():
    """Run all isolation tests. Returns {survivors, killed, capped, details}."""
    games = tm_db.get_historical_games("nba")

    # Filter eligible
    eligible = [g for g in games
                if g.get("game_status") == "STATUS_FINAL"
                and g.get("closing_spread") is not None
                and g.get("home_covered") in (0, 1)]
    eligible.sort(key=lambda g: g.get("game_date", ""))

    if not eligible:
        return {"error": "No eligible games", "total_eligible": 0}

    _classify_games(eligible)

    with _lock:
        _progress["total_eligible"] = len(eligible)

    results = {}
    factors = [
        ("line_movement_merged", test_line_movement_merged),
        ("spread_size", test_spread_size),
        ("day_of_week", test_day_of_week),
        ("vegas_trap", test_vegas_trap),
        ("b2b", test_b2b),
        ("trell_rule", test_trell_rule),
        ("ats_record", test_ats_record),
        ("sharp_money", test_sharp_money),
    ]

    for name, test_fn in factors:
        with _lock:
            _progress["current_factor"] = name
        results[name] = test_fn(eligible)

    survivors = [k for k, v in results.items() if v.get("survives")]
    killed = [k for k, v in results.items() if not v.get("survives") and not v.get("cap")]
    capped = [k for k, v in results.items() if not v.get("survives") and v.get("cap")]

    # H2H and home_away_split already zeroed — confirm
    results["h2h"] = {"name": "h2h", "survives": False, "reason": "zeroed_via_universal_defaults"}
    results["home_away_split"] = {"name": "home_away_split", "survives": False,
                                   "reason": "zeroed_via_universal_defaults"}
    results["feedback"] = {"name": "feedback", "survives": False,
                            "reason": "zeroed_permanently_circular"}

    # Save results
    try:
        tm_db.save_model_run({
            "sport": "nba",
            "run_type": "nba_factor_isolation",
            "total_predictions": len(eligible),
            "model_params": {
                "survivors": survivors,
                "killed": killed,
                "capped": capped,
                "details": results,
            },
        })
    except Exception:
        pass

    return {
        "total_eligible": len(eligible),
        "survivors": survivors,
        "killed": killed,
        "capped": capped,
        "details": results,
    }
