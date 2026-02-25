"""
Walk-Forward Validation — derives scoring weights from training data only,
evaluates on unseen test data to produce honest out-of-sample performance.

Supports two modes:
  - "split": single 70/30 chronological split
  - "rolling": sliding 200-train/50-test windows, step=50

No changes to production scoring code — all weight derivation is self-contained.
"""

import threading
from collections import defaultdict
from copy import deepcopy

from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot, score_line_movement
from rank_analysis import _detect_rank_scam, _detect_spread_discrepancy
from analysis_factors import _analyze_home_away_split, H2H_REVENGE_THRESHOLDS
from constants import (
    wilson_interval, metric_with_ci, MIN_SAMPLES,
    proportion_z_test, UNIVERSAL_DEFAULTS, OVERRIDE_EVIDENCE_THRESHOLDS,
    get_override,
)
from test_model import db as tm_db
from test_model.date_utils import parse_iso_date, parse_game_dt

# ─── Configuration ────────────────────────────────────────────────────────────
ROLLING_TRAIN = 200
ROLLING_TEST = 50
SPLIT_RATIO = 0.70
MIN_FACTOR_FIRES = 30   # Raised from 10 — require more evidence before trusting a factor
MIN_FOLD_TRAIN = 50
MIN_FOLD_TEST = 15
_TEAM_STATE_MAX = 20
_MAX_PREDICTIONS_IN_MEMORY = 200
MIN_GAMES_RELIABLE = 150     # Below this: flag as insufficient, use Wilson CIs
MIN_GAMES_WEIGHT_TUNING = 300  # Below this: lock weight derivation, use production fallbacks

# ─── L2 Regularization ─────────────────────────────────────────────────────────
L2_LAMBDA = 0.001  # Penalizes weight deviation from universal defaults

def _l2_penalty(weights, sport):
    """Compute L2 regularization penalty for deviation from universal defaults."""
    penalty = 0.0
    defaults = UNIVERSAL_DEFAULTS
    fw = weights.get("factor_weights", {})

    for key in ("b2b_bonus", "b2b_penalty", "ats_bonus", "ats_penalty",
                "home_away_split", "h2h_revenge", "h2h_dominance"):
        derived = fw.get(key, 0)
        default = defaults.get(key, 0)
        penalty += (derived - default) ** 2

    penalty += (weights.get("public_slot_bonus", 10) - defaults["public_slot_bonus"]) ** 2
    penalty += (weights.get("line_toward_dog", 0) - defaults["line_toward_dog"]) ** 2
    penalty += (weights.get("line_toward_fav", 0) - defaults["line_toward_fav"]) ** 2

    for val in weights.get("day_penalties", {}).values():
        penalty += val ** 2

    for val in weights.get("spread_buckets", {}).values():
        penalty += val ** 2

    return L2_LAMBDA * penalty


def _l2_constrain_weight(derived_weight, default_weight):
    """Shrink derived weight toward default proportional to lambda."""
    return derived_weight - L2_LAMBDA * 2 * (derived_weight - default_weight)


# ─── Progress tracking ───────────────────────────────────────────────────────
_wf_progress = {}
_wf_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def start_walkforward_thread(sport, mode="split"):
    """Start walk-forward validation in a background thread. Returns immediately."""
    with _wf_lock:
        existing = _wf_progress.get(sport, {})
        if existing.get("status") == "running":
            return False

    t = threading.Thread(target=run_walkforward, args=(sport, mode), daemon=True)
    t.start()
    return True


def get_walkforward_status(sport):
    """Thread-safe progress read."""
    with _wf_lock:
        return dict(_wf_progress.get(sport, {}))


def run_walkforward(sport, mode="split"):
    """
    Main entry point. Loads historical games, builds folds, derives weights
    from training data, evaluates on test data, and saves results.
    """
    # 1. Load eligible games
    games = tm_db.get_historical_games(sport)
    if not games:
        with _wf_lock:
            _wf_progress[sport] = {"status": "error", "message": "No historical games found."}
        return

    eligible = [
        g for g in games
        if g.get("closing_spread") is not None
        and g.get("home_covered") in (0, 1)
        and g.get("game_status") == "STATUS_FINAL"
    ]
    del games

    total = len(eligible)
    insufficient_data = total < MIN_GAMES_RELIABLE
    weight_tuning_locked = total < MIN_GAMES_WEIGHT_TUNING
    min_needed = MIN_FOLD_TRAIN + MIN_FOLD_TEST
    if total < min_needed:
        with _wf_lock:
            _wf_progress[sport] = {
                "status": "error",
                "message": f"Need at least {min_needed} eligible games, have {total}.",
            }
        return

    with _wf_lock:
        _wf_progress[sport] = {
            "status": "running",
            "total_games": total,
            "processed_folds": 0,
            "total_folds": 0,
            "current_fold": "",
            "mode": mode,
            "insufficient_data": insufficient_data,
            "weight_tuning_locked": weight_tuning_locked,
        }

    # 2. Group by date for slate context
    games_by_date = _group_games_by_date(eligible)

    # 3. Build folds
    folds, downgraded = _build_folds(eligible, mode, sport)
    if not folds:
        with _wf_lock:
            _wf_progress[sport] = {
                "status": "error",
                "message": "Could not build any valid folds from available data.",
            }
        return

    with _wf_lock:
        _wf_progress[sport]["total_folds"] = len(folds)
        if downgraded:
            _wf_progress[sport]["downgraded"] = True

    # 4. Process each fold
    fold_results = []
    for fold_idx, (train_slice, test_slice) in enumerate(folds):
        with _wf_lock:
            _wf_progress[sport]["current_fold"] = f"Fold {fold_idx + 1}/{len(folds)}"
            _wf_progress[sport]["processed_folds"] = fold_idx

        # a. Build fresh team_state from training games
        team_state = {}
        train_games_by_date = _group_games_by_date(train_slice)
        for game in train_slice:
            home_st = _get_state(team_state, game["home_team"])
            away_st = _get_state(team_state, game["away_team"])
            _update_team_state(game, home_st, away_st)

        # b. Derive weights (or use production fallbacks if tuning locked)
        if weight_tuning_locked:
            weights = _get_fallback_weights(sport)
        else:
            weights = _derive_weights(train_slice, sport, train_games_by_date)

        # c. Evaluate fold on test data
        test_games_by_date = _group_games_by_date(test_slice)
        # Merge train dates into test for full slate context
        merged_by_date = defaultdict(list)
        for dk, glist in games_by_date.items():
            merged_by_date[dk] = glist
        fold_metrics = _evaluate_fold(test_slice, weights, sport,
                                      deepcopy(team_state), merged_by_date,
                                      insufficient_data=insufficient_data)

        # d. Record fold results
        fold_results.append({
            "fold_idx": fold_idx,
            "train_size": len(train_slice),
            "test_size": len(test_slice),
            "weights_snapshot": _snapshot_weights(weights),
            "metrics": fold_metrics,
        })

    # 5. Aggregate across folds
    aggregated = _aggregate_folds(fold_results, insufficient_data=insufficient_data)

    # 6. Build comparison with in-sample
    comparison = _build_comparison(sport, aggregated)

    # 7. Save to database
    tm_db.save_model_run({
        "sport": sport,
        "run_type": "walkforward",
        "accuracy": aggregated.get("mean_accuracy"),
        "roi": aggregated.get("mean_roi"),
        "clv_avg": None,
        "total_predictions": aggregated.get("total_test_games"),
        "qualified_bets": aggregated.get("mean_qualified_bets"),
        "feature_importances": aggregated.get("averaged_factor_lifts", {}),
        "model_params": {
            "mode": mode,
            "downgraded": downgraded,
            "num_folds": len(folds),
            "sport": sport,
            "total_eligible": total,
            "insufficient_data": insufficient_data,
            "weight_tuning_locked": weight_tuning_locked,
            "data_warning": _build_data_warning(total, insufficient_data, weight_tuning_locked),
            "train_sizes": [f["train_size"] for f in fold_results],
            "test_sizes": [f["test_size"] for f in fold_results],
            "sample_weights": fold_results[-1]["weights_snapshot"] if fold_results else {},
        },
        "threshold_analysis": aggregated.get("threshold_analysis", {}),
        "predictions": aggregated.get("last_predictions", []),
    })

    # 8. Final progress
    with _wf_lock:
        _wf_progress[sport] = {
            "status": "complete",
            "total_games": total,
            "processed_folds": len(folds),
            "total_folds": len(folds),
            "mode": mode,
            "downgraded": downgraded,
            "insufficient_data": insufficient_data,
            "weight_tuning_locked": weight_tuning_locked,
            "data_warning": _build_data_warning(total, insufficient_data, weight_tuning_locked),
            "metrics": aggregated,
            "comparison": comparison,
        }

    return aggregated


# ═══════════════════════════════════════════════════════════════════════════════
# Team State Helpers (copied from rules_backtest — private, not worth importing)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_state(team_state, team):
    if team not in team_state:
        team_state[team] = {
            "dates": [],
            "results": [],
            "scores": [],
            "opp_scores": [],
            "opponents": [],
            "margins": [],
            "ats_covers": 0,
            "ats_total": 0,
        }
    return team_state[team]


def _update_team_state(game, home_st, away_st):
    home_score = game.get("home_score", 0) or 0
    away_score = game.get("away_score", 0) or 0
    home_won = 1 if home_score > away_score else 0
    game_date = game.get("game_date", "")
    home_covered = game.get("home_covered")

    home_st["results"].append(home_won)
    home_st["scores"].append(home_score)
    home_st["opp_scores"].append(away_score)
    home_st["dates"].append(game_date)
    home_st["opponents"].append(game["away_team"])
    home_st["margins"].append(home_score - away_score)

    away_st["results"].append(1 - home_won)
    away_st["scores"].append(away_score)
    away_st["opp_scores"].append(home_score)
    away_st["dates"].append(game_date)
    away_st["opponents"].append(game["home_team"])
    away_st["margins"].append(away_score - home_score)

    for st in (home_st, away_st):
        for key in ("results", "scores", "opp_scores", "dates", "opponents", "margins"):
            if len(st[key]) > _TEAM_STATE_MAX:
                st[key] = st[key][-_TEAM_STATE_MAX:]

    if home_covered == 1:
        home_st["ats_covers"] += 1
        home_st["ats_total"] += 1
        away_st["ats_total"] += 1
    elif home_covered == 0:
        away_st["ats_covers"] += 1
        home_st["ats_total"] += 1
        away_st["ats_total"] += 1


def _is_b2b_from_state(team_st, game_date_str):
    if not team_st["dates"]:
        return False
    last_dt = parse_iso_date(team_st["dates"][-1])
    game_dt = parse_iso_date(game_date_str)
    if last_dt is None or game_dt is None:
        return False
    return abs((game_dt - last_dt).days) <= 1


def _find_last_h2h_margin(lean_st, opp_name):
    for i in range(len(lean_st["opponents"]) - 1, -1, -1):
        if lean_st["opponents"][i] == opp_name:
            return lean_st["margins"][i]
    return None


def _check_nfl_trend_from_state(home_st, away_st):
    def classify_trend(results):
        last4 = results[-4:] if len(results) >= 4 else []
        if len(last4) < 4:
            return None
        wins = sum(last4)
        if wins <= 1:
            return "bounce-back"
        elif wins >= 3:
            return "regression"
        return None
    return classify_trend(home_st["results"]) is not None or \
           classify_trend(away_st["results"]) is not None


def _check_nfl_ou_from_state(home_st, away_st, over_under):
    if over_under > 50.5:
        return True
    home_avg = sum(home_st["scores"][-4:]) / max(len(home_st["scores"][-4:]), 1) if home_st["scores"] else 0
    away_avg = sum(away_st["scores"][-4:]) / max(len(away_st["scores"][-4:]), 1) if away_st["scores"] else 0
    combined = home_avg + away_avg
    return abs(over_under - combined) >= 6


# ═══════════════════════════════════════════════════════════════════════════════
# Slot Classification Helper
# ═══════════════════════════════════════════════════════════════════════════════

def _group_games_by_date(games):
    by_date = defaultdict(list)
    for game in games:
        gd = game.get("game_date", "")
        date_key = gd[:10] if gd else "unknown"
        by_date[date_key].append(game)
    for dk in by_date:
        by_date[dk].sort(key=lambda g: g.get("game_date", ""))
    return by_date


def _classify_game_slot(game, games_by_date, sport):
    """Classify a game's slot type. Returns (slot_type, day_of_week, hour, minute) or None."""
    game_date_str = game.get("game_date", "")
    local_dt = parse_game_dt(game_date_str, sport)
    if local_dt is None:
        return None

    day_of_week = local_dt.strftime("%A")
    hour, minute = local_dt.hour, local_dt.minute

    date_key = game_date_str[:10]
    date_games = games_by_date.get(date_key, [])
    total_games_on_slate = len(date_games)
    game_index = 0
    for idx, dg in enumerate(date_games):
        if dg.get("event_id") == game.get("event_id"):
            game_index = idx
            break
    is_first_game = (game_index == 0)

    # NFL: detect last non-SNF Sunday game
    is_last_sunday_game = False
    if sport == "nfl" and day_of_week.lower() == "sunday":
        snf_mins = 17 * 60 + 20
        for dg in reversed(date_games):
            dg_dt = parse_game_dt(dg.get("game_date", ""), sport)
            if dg_dt:
                dg_mins = dg_dt.hour * 60 + dg_dt.minute
                if abs(dg_mins - snf_mins) > 30:
                    if dg.get("event_id") == game.get("event_id"):
                        is_last_sunday_game = True
                    break

    if sport == "nfl":
        slot_type = classify_slot(day_of_week, hour, minute,
                                  sport="nfl",
                                  is_last_sunday_game=is_last_sunday_game)
    elif sport in ("cfb", "cbb"):
        slot_type = classify_slot(day_of_week, hour, minute, sport=sport)
    elif sport == "nhl":
        slot_type = classify_slot(day_of_week, hour, minute,
                                  sport="nhl",
                                  total_games_on_slate=total_games_on_slate,
                                  game_index=game_index)
    else:
        # NBA
        if is_first_game:
            slot_type = first_game_slot_override(day_of_week)
        else:
            slot_type = classify_slot(day_of_week, hour, minute)

    return slot_type, day_of_week, hour, minute


# ═══════════════════════════════════════════════════════════════════════════════
# Game Context Builder
# ═══════════════════════════════════════════════════════════════════════════════

def _build_game_context(game, home_st, away_st, games_by_date, sport):
    """
    Extracts all factor signals into a flat dict for scoring.
    Returns None if game should be skipped.
    """
    slot_result = _classify_game_slot(game, games_by_date, sport)
    if slot_result is None:
        return None
    slot_type, day_of_week, hour, minute = slot_result

    if slot_type == "skip":
        return None

    home = game["home_team"]
    away = game["away_team"]
    closing_spread = game["closing_spread"]
    opening_spread = game.get("opening_spread")
    home_rank = game.get("home_rank")
    away_rank = game.get("away_rank")
    over_under = game.get("over_under")
    game_date_str = game.get("game_date", "")

    # Line movement
    line_confirms = False
    line_magnitude = 0.0
    line_toward_dog = False
    line_toward_fav = False
    if opening_spread is not None and closing_spread is not None:
        movement, line_magnitude = detect_movement(opening_spread, closing_spread)
        line_confirms = confirms_slot(movement, slot_type)
        raw_movement = closing_spread - opening_spread
        if closing_spread < 0:
            line_toward_dog = raw_movement > 0.5
            line_toward_fav = raw_movement < -0.5
        else:
            line_toward_dog = raw_movement < -0.5
            line_toward_fav = raw_movement > 0.5

    # Rank analysis (CFB/CBB only)
    rank_scam_applies = False
    spread_disc_applies = False
    if sport in ("cfb", "cbb"):
        rank_scam = _detect_rank_scam(home_rank, away_rank, closing_spread, slot_type)
        spread_disc = _detect_spread_discrepancy(home_rank, away_rank, closing_spread, slot_type, sport=sport)
        rank_scam_applies = rank_scam.get("is_rank_scam", False)
        spread_disc_applies = spread_disc.get("is_discrepancy", False)

    # Home/away split — computed per-lean later, store raw data
    home_away_applies = False  # will be set per lean determination

    # B2B detection
    b2b_bonus = False
    b2b_penalty = False
    if sport in ("nba", "nhl"):
        lean_b2b_home = _is_b2b_from_state(home_st, game_date_str)
        lean_b2b_away = _is_b2b_from_state(away_st, game_date_str)
    else:
        lean_b2b_home = False
        lean_b2b_away = False

    # H2H (precompute for both directions)
    threshold = H2H_REVENGE_THRESHOLDS.get(sport, 10)
    h2h_margin_home = _find_last_h2h_margin(home_st, away)
    h2h_margin_away = _find_last_h2h_margin(away_st, home)

    # Vegas trap (NBA only)
    vegas_trap_bonus = 0
    if sport == "nba" and slot_type in ("vegas", "trap") and abs(closing_spread) >= 7:
        if closing_spread < 0:
            fav_st = home_st
        else:
            fav_st = away_st
        fav_wins_7 = sum(fav_st["results"][-7:]) if len(fav_st["results"]) >= 5 else None
        if fav_wins_7 is not None and fav_wins_7 <= 2:
            vegas_trap_bonus = 5
            if closing_spread < 0:
                dog_st = away_st
            else:
                dog_st = home_st
            dog_wins_7 = sum(dog_st["results"][-7:]) if len(dog_st["results"]) >= 5 else None
            if dog_wins_7 is not None and dog_wins_7 <= 2:
                vegas_trap_bonus = 7

    # NFL trend discrepancy
    trend_disc_applies = False
    if sport == "nfl" and slot_type == "vegas":
        trend_disc_applies = _check_nfl_trend_from_state(home_st, away_st)

    # NFL O/U discrepancy
    ou_disc_applies = False
    if sport == "nfl" and slot_type == "vegas" and over_under is not None:
        ou_disc_applies = _check_nfl_ou_from_state(home_st, away_st, over_under)

    # ATS record
    ats_bonus_home = False
    ats_penalty_home = False
    ats_bonus_away = False
    ats_penalty_away = False
    if home_st["ats_total"] >= MIN_SAMPLES["ats"]:
        ats_rate = home_st["ats_covers"] / home_st["ats_total"] * 100
        if ats_rate > 60:
            ats_bonus_home = True
        elif ats_rate < 40:
            ats_penalty_home = True
    if away_st["ats_total"] >= MIN_SAMPLES["ats"]:
        ats_rate = away_st["ats_covers"] / away_st["ats_total"] * 100
        if ats_rate > 60:
            ats_bonus_away = True
        elif ats_rate < 40:
            ats_penalty_away = True

    return {
        "slot_type": slot_type,
        "day_of_week": day_of_week,
        "closing_spread": closing_spread,
        "opening_spread": opening_spread,
        "line_confirms": line_confirms,
        "line_magnitude": line_magnitude,
        "line_toward_dog": line_toward_dog,
        "line_toward_fav": line_toward_fav,
        "lean_b2b_home": lean_b2b_home,
        "lean_b2b_away": lean_b2b_away,
        "h2h_margin_home": h2h_margin_home,
        "h2h_margin_away": h2h_margin_away,
        "h2h_threshold": threshold,
        "rank_scam_applies": rank_scam_applies,
        "spread_disc_applies": spread_disc_applies,
        "trend_disc_applies": trend_disc_applies,
        "ou_disc_applies": ou_disc_applies,
        "vegas_trap_bonus": vegas_trap_bonus,
        "ats_bonus_home": ats_bonus_home,
        "ats_penalty_home": ats_penalty_home,
        "ats_bonus_away": ats_bonus_away,
        "ats_penalty_away": ats_penalty_away,
        "home_team": home,
        "away_team": away,
        "home_rank": home_rank,
        "away_rank": away_rank,
        "home_covered": game.get("home_covered"),
        "game_date": game_date_str,
        "sport": sport,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Weight Derivation (the core innovation)
# ═══════════════════════════════════════════════════════════════════════════════

def _derive_weights(train_games, sport, train_games_by_date):
    """
    Derives all scoring weights entirely from training data.
    Two-pass approach + threshold sweep.
    """
    # Pass 1: raw statistics — dog cover rates by slot, day, spread bucket
    pass1 = _pass1_raw_stats(train_games, sport, train_games_by_date)

    # Pass 2: factor lifts — replay with pass1 lean, measure each factor's lift
    pass2 = _pass2_factor_lifts(train_games, sport, train_games_by_date, pass1)

    # Combine into weights dict
    weights = {
        "lean": pass1["lean"],
        "lean_public": pass1["lean_public"],
        "lean_vegas": pass1["lean_vegas"],
        "weak_lean": pass1.get("weak_lean", False),
        "public_slot_bonus": pass1["public_slot_bonus"],
        "day_penalties": pass1["day_penalties"],
        "spread_buckets": pass1["spread_buckets"],
        "factor_weights": pass2["factor_weights"],
        "line_toward_dog": pass2["line_toward_dog"],
        "line_toward_fav": pass2["line_toward_fav"],
        "line_movement_tiers": pass2["line_movement_tiers"],
    }

    # Threshold sweep
    weights["thresholds"] = _sweep_thresholds(train_games, sport,
                                               train_games_by_date, weights)

    return weights


def _pass1_raw_stats(train_games, sport, games_by_date):
    """
    Pass 1: Replay training games, classify slots, record raw outcomes.
    No lean determination yet — just track dog cover rates.
    """
    slot_outcomes = defaultdict(lambda: {"dog_cover": 0, "total": 0})
    day_outcomes = defaultdict(lambda: {"dog_cover": 0, "total": 0})
    spread_buckets = defaultdict(lambda: {"dog_cover": 0, "total": 0})

    SPREAD_BUCKET_EDGES = [(0, 3), (3, 5), (5, 7), (7, 10), (10, 13), (13, 100)]

    for game in train_games:
        slot_result = _classify_game_slot(game, games_by_date, sport)
        if slot_result is None:
            continue
        slot_type, day_of_week, _, _ = slot_result
        if slot_type == "skip":
            continue

        closing_spread = game["closing_spread"]
        if closing_spread is None:
            continue

        home_covered = game.get("home_covered")
        if home_covered is None:
            continue

        # Underdog = away if home favored (spread < 0), home if away favored
        dog_covered = (home_covered == 0) if closing_spread < 0 else (home_covered == 1)

        slot_outcomes[slot_type]["total"] += 1
        if dog_covered:
            slot_outcomes[slot_type]["dog_cover"] += 1

        day_outcomes[day_of_week.lower()]["total"] += 1
        if dog_covered:
            day_outcomes[day_of_week.lower()]["dog_cover"] += 1

        spread_abs = abs(closing_spread)
        for lo, hi in SPREAD_BUCKET_EDGES:
            if lo <= spread_abs < hi:
                key = f"{lo}-{hi}"
                spread_buckets[key]["total"] += 1
                if dog_covered:
                    spread_buckets[key]["dog_cover"] += 1
                break

    # Derive lean direction with significance testing
    overall_dog_cover = sum(d["dog_cover"] for d in slot_outcomes.values())
    overall_total = sum(d["total"] for d in slot_outcomes.values())
    overall_rate = _safe_rate({"dog_cover": overall_dog_cover, "total": overall_total})

    public_rate = _safe_rate(slot_outcomes["public"])
    vegas_rate = _safe_rate(slot_outcomes["vegas"])

    lean_thresh = OVERRIDE_EVIDENCE_THRESHOLDS["lean_direction"]
    total_lean_games = slot_outcomes["public"]["total"] + slot_outcomes["vegas"]["total"]

    # Require sufficient data + statistical significance to flip lean from default
    if total_lean_games >= lean_thresh["min_games"]:
        _, p_pub = proportion_z_test(
            slot_outcomes["public"]["dog_cover"],
            slot_outcomes["public"]["total"], 0.50)
        _, p_veg = proportion_z_test(
            slot_outcomes["vegas"]["dog_cover"],
            slot_outcomes["vegas"]["total"], 0.50)

        if (public_rate > 55 and vegas_rate > 55
                and p_pub < lean_thresh["p_threshold"]
                and p_veg < lean_thresh["p_threshold"]):
            lean = "always_underdog"
            lean_public = "underdog"
            lean_vegas = "underdog"
        elif (public_rate < 45 and vegas_rate < 45
              and p_pub < lean_thresh["p_threshold"]
              and p_veg < lean_thresh["p_threshold"]):
            lean = "always_favorite"
            lean_public = "favorite"
            lean_vegas = "favorite"
        else:
            lean = "slot_dependent"
            lean_public = "underdog" if public_rate >= 50 else "favorite"
            lean_vegas = "underdog" if vegas_rate >= 50 else "favorite"
    else:
        # Insufficient data — use default slot_dependent
        lean = "slot_dependent"
        lean_public = "underdog" if public_rate >= 50 else "favorite"
        lean_vegas = "underdog" if vegas_rate >= 50 else "favorite"

    weak_lean = 48 <= public_rate <= 52 or 48 <= vegas_rate <= 52

    # Day penalties: require min_games + z-test significance
    day_thresh = OVERRIDE_EVIDENCE_THRESHOLDS["day_penalty"]
    day_penalties = {}
    for day, data in day_outcomes.items():
        rate = _safe_rate(data)
        if data["total"] >= day_thresh["min_games"] and rate < 50:
            _, p_val = proportion_z_test(
                data["dog_cover"], data["total"], overall_rate / 100)
            if p_val < day_thresh["p_threshold"]:
                day_penalties[day] = -3

    # Spread bucket adjustments: require min_games + z-test significance
    spread_thresh = OVERRIDE_EVIDENCE_THRESHOLDS["spread_bucket"]
    spread_adj = {}
    for bucket_key, data in spread_buckets.items():
        if data["total"] < spread_thresh["min_games"]:
            spread_adj[bucket_key] = 0
            continue
        rate = _safe_rate(data)
        _, p_val = proportion_z_test(
            data["dog_cover"], data["total"], overall_rate / 100)
        if p_val < spread_thresh["p_threshold"]:
            if rate > 60:
                spread_adj[bucket_key] = 3
            elif rate < 45:
                spread_adj[bucket_key] = -3
            else:
                spread_adj[bucket_key] = 0
        else:
            spread_adj[bucket_key] = 0

    # Public slot bonus: based on accuracy gap
    public_total = slot_outcomes["public"]["total"]
    if public_total >= 10:
        bonus = max(0, min(10, round((public_rate - 50) * 0.5)))
    else:
        bonus = 0

    return {
        "lean": lean,
        "lean_public": lean_public,
        "lean_vegas": lean_vegas,
        "weak_lean": weak_lean,
        "day_penalties": day_penalties,
        "spread_buckets": spread_adj,
        "public_slot_bonus": bonus,
        "slot_rates": {s: _safe_rate(d) for s, d in slot_outcomes.items()},
    }


def _pass2_factor_lifts(train_games, sport, games_by_date, pass1):
    """
    Pass 2: Re-replay training games using Pass 1's derived lean.
    For each game, detect all factors, track fires + accuracy.
    """
    team_state = {}
    factor_tracker = defaultdict(lambda: {"fired": 0, "correct_when_fired": 0,
                                           "not_fired": 0, "correct_when_not_fired": 0})
    # Line movement magnitude buckets
    line_mag_tracker = defaultdict(lambda: {"total": 0, "correct": 0})
    # Line direction tracker
    line_dir_tracker = {"toward_dog": {"total": 0, "correct": 0},
                        "toward_fav": {"total": 0, "correct": 0},
                        "neutral": {"total": 0, "correct": 0}}

    warmup_count = 0
    MIN_WARMUP = 10

    for game in train_games:
        home = game["home_team"]
        away = game["away_team"]
        home_st = _get_state(team_state, home)
        away_st = _get_state(team_state, away)

        if warmup_count < MIN_WARMUP:
            _update_team_state(game, home_st, away_st)
            warmup_count += 1
            continue

        ctx = _build_game_context(game, home_st, away_st, games_by_date, sport)
        if ctx is None:
            _update_team_state(game, home_st, away_st)
            continue

        # Determine lean using pass1 results
        lean_team = _determine_lean_from_pass1(pass1, ctx["slot_type"],
                                                home, away, ctx["closing_spread"])
        if lean_team is None:
            _update_team_state(game, home_st, away_st)
            continue

        lean_is_home = (lean_team == home)

        # Resolve lean-dependent factors
        b2b_bonus, b2b_penalty = _resolve_b2b(ctx, lean_is_home)
        h2h_revenge, h2h_dominance = _resolve_h2h(ctx, lean_is_home)
        ats_bonus, ats_penalty = _resolve_ats(ctx, lean_is_home)
        home_away_applies = _analyze_home_away_split(lean_team, home,
                                                      ctx["slot_type"], ctx["closing_spread"])

        # Evaluate correctness
        actual_covered = ctx["home_covered"]
        correct = (actual_covered == 1) if lean_is_home else (actual_covered == 0)

        # Track all factors
        _track_factor(factor_tracker, "slot_public", ctx["slot_type"] == "public", correct)
        _track_factor(factor_tracker, "line_movement", ctx["line_confirms"], correct)
        _track_factor(factor_tracker, "rank_scam", ctx["rank_scam_applies"], correct)
        _track_factor(factor_tracker, "spread_discrepancy", ctx["spread_disc_applies"], correct)
        _track_factor(factor_tracker, "home_away_split", home_away_applies, correct)
        _track_factor(factor_tracker, "b2b_bonus", b2b_bonus, correct)
        _track_factor(factor_tracker, "b2b_penalty", b2b_penalty, correct)
        _track_factor(factor_tracker, "h2h_revenge", h2h_revenge, correct)
        _track_factor(factor_tracker, "h2h_dominance", h2h_dominance, correct)
        _track_factor(factor_tracker, "vegas_trap", ctx["vegas_trap_bonus"] > 0, correct)
        _track_factor(factor_tracker, "trend_discrepancy", ctx["trend_disc_applies"], correct)
        _track_factor(factor_tracker, "ou_discrepancy", ctx["ou_disc_applies"], correct)
        _track_factor(factor_tracker, "ats_bonus", ats_bonus, correct)
        _track_factor(factor_tracker, "ats_penalty", ats_penalty, correct)

        # Line movement magnitude tracking
        if ctx["line_confirms"] and ctx["line_magnitude"] >= 1:
            if ctx["line_magnitude"] < 2:
                bucket = "1-2"
            elif ctx["line_magnitude"] < 3:
                bucket = "2-3"
            else:
                bucket = "3+"
            line_mag_tracker[bucket]["total"] += 1
            if correct:
                line_mag_tracker[bucket]["correct"] += 1

        # Line direction tracking
        if ctx["line_toward_dog"]:
            line_dir_tracker["toward_dog"]["total"] += 1
            if correct:
                line_dir_tracker["toward_dog"]["correct"] += 1
        elif ctx["line_toward_fav"]:
            line_dir_tracker["toward_fav"]["total"] += 1
            if correct:
                line_dir_tracker["toward_fav"]["correct"] += 1
        else:
            line_dir_tracker["neutral"]["total"] += 1
            if correct:
                line_dir_tracker["neutral"]["correct"] += 1

        _update_team_state(game, home_st, away_st)

    # Derive factor weights from lifts with significance testing
    factor_thresh = OVERRIDE_EVIDENCE_THRESHOLDS["factor_weight"]
    # Compute baseline rate from all tracked games
    all_fired = sum(d["fired"] for d in factor_tracker.values())
    all_correct_fired = sum(d["correct_when_fired"] for d in factor_tracker.values())
    all_not_fired = sum(d["not_fired"] for d in factor_tracker.values())
    all_correct_not = sum(d["correct_when_not_fired"] for d in factor_tracker.values())
    total_games_tracked = all_fired + all_not_fired
    baseline_rate = ((all_correct_fired + all_correct_not) / total_games_tracked
                     if total_games_tracked > 0 else 0.50)

    factor_weights = {}
    for factor_name, data in factor_tracker.items():
        fired = data["fired"]
        not_fired = data["not_fired"]
        if fired > 0:
            acc_fired = data["correct_when_fired"] / fired * 100
        else:
            acc_fired = 0
        if not_fired > 0:
            acc_not_fired = data["correct_when_not_fired"] / not_fired * 100
        else:
            acc_not_fired = 0

        lift = acc_fired - acc_not_fired if fired > 0 and not_fired > 0 else 0

        if fired < MIN_FACTOR_FIRES:
            # Insufficient fires — zero out
            factor_weights[factor_name] = 0
        elif fired >= factor_thresh["min_games"]:
            # Full evidence: require z-test significance at p < 0.10
            _, p_val = proportion_z_test(
                data["correct_when_fired"], fired, baseline_rate)
            if p_val < factor_thresh["p_threshold"]:
                # Significant — apply full lift-based mapping
                if lift >= 8:
                    factor_weights[factor_name] = 5
                elif lift >= 5:
                    factor_weights[factor_name] = 3
                elif lift >= 2:
                    factor_weights[factor_name] = 2
                elif lift >= 0:
                    factor_weights[factor_name] = 1
                elif lift >= -2:
                    factor_weights[factor_name] = 0
                else:
                    factor_weights[factor_name] = max(-5, round(lift / 2))
            else:
                # Not significant — zero out
                factor_weights[factor_name] = 0
        else:
            # Between MIN_FACTOR_FIRES and factor_thresh — cap weight at ±2
            if lift >= 5:
                factor_weights[factor_name] = 2
            elif lift >= 2:
                factor_weights[factor_name] = 2
            elif lift >= 0:
                factor_weights[factor_name] = 1
            elif lift >= -2:
                factor_weights[factor_name] = 0
            else:
                factor_weights[factor_name] = max(-2, round(lift / 2))

    # L2-constrain factor weights toward universal defaults
    for key in factor_weights:
        default_val = UNIVERSAL_DEFAULTS.get(key, 0)
        factor_weights[key] = round(
            _l2_constrain_weight(factor_weights[key], default_val), 1)

    # Line direction weights
    dog_data = line_dir_tracker["toward_dog"]
    fav_data = line_dir_tracker["toward_fav"]
    neutral_data = line_dir_tracker["neutral"]
    neutral_rate = _safe_rate_simple(neutral_data)

    if dog_data["total"] >= MIN_FACTOR_FIRES:
        dog_rate = _safe_rate_simple(dog_data)
        dog_lift = dog_rate - neutral_rate
        line_toward_dog_w = max(0, min(5, round(dog_lift / 2)))
    else:
        line_toward_dog_w = 0

    if fav_data["total"] >= MIN_FACTOR_FIRES:
        fav_rate = _safe_rate_simple(fav_data)
        fav_lift = fav_rate - neutral_rate
        line_toward_fav_w = max(-5, min(0, round(fav_lift / 2)))
    else:
        line_toward_fav_w = 0

    # Line movement tier scores from accuracy by magnitude bucket
    line_movement_tiers = {}
    for bucket, data in line_mag_tracker.items():
        if data["total"] >= 5:
            rate = _safe_rate_simple(data)
            if rate > 65:
                line_movement_tiers[bucket] = 5
            elif rate > 58:
                line_movement_tiers[bucket] = 3
            elif rate > 52:
                line_movement_tiers[bucket] = 2
            else:
                line_movement_tiers[bucket] = 0
        else:
            line_movement_tiers[bucket] = 0

    return {
        "factor_weights": factor_weights,
        "factor_tracker": {k: dict(v) for k, v in factor_tracker.items()},
        "line_toward_dog": line_toward_dog_w,
        "line_toward_fav": line_toward_fav_w,
        "line_movement_tiers": line_movement_tiers,
    }


def _sweep_thresholds(train_games, sport, games_by_date, weights):
    """
    Score all training games with derived weights, sweep score cutoffs.
    """
    team_state = {}
    scored = []
    warmup_count = 0
    MIN_WARMUP = 10

    for game in train_games:
        home = game["home_team"]
        away = game["away_team"]
        home_st = _get_state(team_state, home)
        away_st = _get_state(team_state, away)

        if warmup_count < MIN_WARMUP:
            _update_team_state(game, home_st, away_st)
            warmup_count += 1
            continue

        ctx = _build_game_context(game, home_st, away_st, games_by_date, sport)
        if ctx is None:
            _update_team_state(game, home_st, away_st)
            continue

        lean_team = _determine_lean_from_weights(weights, ctx["slot_type"],
                                                  ctx["home_team"], ctx["away_team"],
                                                  ctx["closing_spread"])
        if lean_team is None:
            _update_team_state(game, home_st, away_st)
            continue

        lean_is_home = (lean_team == ctx["home_team"])
        score, _ = _score_game_with_weights(ctx, weights, lean_is_home)
        actual_covered = ctx["home_covered"]
        correct = (actual_covered == 1) if lean_is_home else (actual_covered == 0)
        scored.append({"score": score, "correct": correct})

        _update_team_state(game, home_st, away_st)

    if not scored:
        return {"lean": 5, "strong": 15}

    # L2 penalty for this weight set
    l2_pen = _l2_penalty(weights, sport)

    # Sweep cutoffs 3-20
    lean_threshold = None
    strong_threshold = None

    for cutoff in range(3, 21):
        qualified = [s for s in scored if s["score"] >= cutoff]
        count = len(qualified)
        if count < 5:
            continue
        acc = sum(1 for s in qualified if s["correct"]) / count * 100
        penalized_acc = acc - l2_pen

        if lean_threshold is None and penalized_acc >= 52.4 and count >= 20:
            lean_threshold = cutoff
        if strong_threshold is None and penalized_acc >= 60 and count >= 10:
            strong_threshold = cutoff

    # Fallbacks: percentile-based
    all_scores = sorted([s["score"] for s in scored])
    if lean_threshold is None:
        idx = int(len(all_scores) * 0.75)
        lean_threshold = all_scores[idx] if idx < len(all_scores) else 5
    if strong_threshold is None:
        idx = int(len(all_scores) * 0.90)
        strong_threshold = all_scores[idx] if idx < len(all_scores) else 15

    # Ensure strong > lean
    if strong_threshold <= lean_threshold:
        strong_threshold = lean_threshold + 3

    return {"lean": lean_threshold, "strong": strong_threshold}


# ═══════════════════════════════════════════════════════════════════════════════
# Self-Contained Scoring
# ═══════════════════════════════════════════════════════════════════════════════

def _determine_lean_from_pass1(pass1, slot_type, home, away, spread):
    """Determine lean using pass1 results."""
    if spread is None:
        return None

    lean_config = pass1["lean"]

    if lean_config == "always_underdog":
        return away if spread < 0 else home
    elif lean_config == "always_favorite":
        return home if spread < 0 else away
    else:
        # slot_dependent
        if slot_type in ("public", "caution"):
            sl = pass1["lean_public"]
        else:
            sl = pass1["lean_vegas"]

        if sl == "underdog":
            return away if spread < 0 else home
        else:
            return home if spread < 0 else away


def _determine_lean_from_weights(weights, slot_type, home, away, spread):
    """Uses weights["lean"] config to pick home/away team."""
    if spread is None:
        return None

    lean_config = weights["lean"]

    if lean_config == "always_underdog":
        return away if spread < 0 else home
    elif lean_config == "always_favorite":
        return home if spread < 0 else away
    else:
        # slot_dependent
        if slot_type in ("public", "caution"):
            sl = weights["lean_public"]
        else:
            sl = weights["lean_vegas"]

        if sl == "underdog":
            return away if spread < 0 else home
        else:
            return home if spread < 0 else away


def _score_game_with_weights(ctx, weights, lean_is_home):
    """
    Score a game using derived weights instead of hardcoded production values.
    Returns (score, breakdown).
    """
    breakdown = {}
    fw = weights["factor_weights"]

    # Public slot bonus
    if ctx["slot_type"] == "public":
        breakdown["slot"] = weights["public_slot_bonus"]
    else:
        breakdown["slot"] = 0

    # Line movement — use derived tiers
    if ctx["line_confirms"] and ctx["line_magnitude"] >= 1:
        mag = ctx["line_magnitude"]
        if mag < 2:
            tier_key = "1-2"
        elif mag < 3:
            tier_key = "2-3"
        else:
            tier_key = "3+"
        breakdown["line_movement"] = weights["line_movement_tiers"].get(tier_key, 0)
    else:
        breakdown["line_movement"] = 0

    # Line direction
    if ctx["line_toward_dog"]:
        breakdown["line_direction"] = weights["line_toward_dog"]
    elif ctx["line_toward_fav"]:
        breakdown["line_direction"] = weights["line_toward_fav"]
    else:
        breakdown["line_direction"] = 0

    # Resolve lean-dependent factors
    b2b_bonus, b2b_penalty = _resolve_b2b(ctx, lean_is_home)
    h2h_revenge, h2h_dominance = _resolve_h2h(ctx, lean_is_home)
    ats_bonus, ats_penalty = _resolve_ats(ctx, lean_is_home)
    home = ctx["home_team"]
    lean_team = home if lean_is_home else ctx["away_team"]
    home_away_applies = _analyze_home_away_split(lean_team, home,
                                                  ctx["slot_type"], ctx["closing_spread"])

    # Factor-based scores from derived weights
    breakdown["rank_scam"] = fw.get("rank_scam", 0) if ctx["rank_scam_applies"] else 0
    breakdown["spread_discrepancy"] = fw.get("spread_discrepancy", 0) if ctx["spread_disc_applies"] else 0
    breakdown["trend_discrepancy"] = fw.get("trend_discrepancy", 0) if ctx["trend_disc_applies"] else 0
    breakdown["ou_discrepancy"] = fw.get("ou_discrepancy", 0) if ctx["ou_disc_applies"] else 0
    breakdown["vegas_trap"] = fw.get("vegas_trap", 0) if ctx["vegas_trap_bonus"] > 0 else 0

    if b2b_bonus:
        breakdown["b2b"] = fw.get("b2b_bonus", 0)
    elif b2b_penalty:
        breakdown["b2b"] = fw.get("b2b_penalty", 0)
    else:
        breakdown["b2b"] = 0

    if ats_bonus:
        breakdown["ats_record"] = fw.get("ats_bonus", 0)
    elif ats_penalty:
        breakdown["ats_record"] = fw.get("ats_penalty", 0)
    else:
        breakdown["ats_record"] = 0

    breakdown["home_away_split"] = fw.get("home_away_split", 0) if home_away_applies else 0

    if h2h_revenge:
        breakdown["head_to_head"] = fw.get("h2h_revenge", 0)
    elif h2h_dominance:
        breakdown["head_to_head"] = fw.get("h2h_dominance", 0)
    else:
        breakdown["head_to_head"] = 0

    # Day penalties from derived weights
    day_key = ctx["day_of_week"].lower()
    breakdown["day_penalty"] = weights["day_penalties"].get(day_key, 0)

    # Spread bucket adjustments
    spread_adj = 0
    if ctx["closing_spread"] is not None:
        spread_abs = abs(ctx["closing_spread"])
        SPREAD_BUCKET_EDGES = [(0, 3), (3, 5), (5, 7), (7, 10), (10, 13), (13, 100)]
        for lo, hi in SPREAD_BUCKET_EDGES:
            if lo <= spread_abs < hi:
                bucket_key = f"{lo}-{hi}"
                spread_adj = weights["spread_buckets"].get(bucket_key, 0)
                break
    breakdown["spread_penalty"] = spread_adj

    # Trell, public betting, feedback — not replayable, always 0
    breakdown["trell"] = 0
    breakdown["public_betting"] = 0
    breakdown["feedback"] = 0

    total = sum(breakdown.values())
    total = max(total, 0)
    return total, breakdown


def _get_rec_from_weights(score, slot_type, weights):
    """Determine recommendation from derived thresholds."""
    thresholds = weights["thresholds"]
    if score >= thresholds["strong"]:
        return "STRONG PLAY"
    if score >= thresholds["lean"]:
        return "LEAN"
    return "MONITOR"


# ═══════════════════════════════════════════════════════════════════════════════
# Walk-Forward Loop
# ═══════════════════════════════════════════════════════════════════════════════

def _build_folds(eligible, mode, sport):
    """
    Build train/test folds from eligible games.
    Returns (list of (train_slice, test_slice), downgraded).
    """
    total = len(eligible)
    downgraded = False

    if mode == "rolling":
        if total < ROLLING_TRAIN + ROLLING_TEST:
            # Auto-downgrade to split
            mode = "split"
            downgraded = True

    if mode == "split":
        split_idx = int(total * SPLIT_RATIO)
        train = eligible[:split_idx]
        test = eligible[split_idx:]
        if len(train) < MIN_FOLD_TRAIN or len(test) < MIN_FOLD_TEST:
            return [], False
        return [(train, test)], downgraded

    # Rolling mode
    folds = []
    start = 0
    while start + ROLLING_TRAIN + ROLLING_TEST <= total:
        train_end = start + ROLLING_TRAIN
        test_end = train_end + ROLLING_TEST
        train = eligible[start:train_end]
        test = eligible[train_end:test_end]
        folds.append((train, test))
        start += ROLLING_TEST  # Non-overlapping test windows

    if not folds:
        # Fallback to split
        return _build_folds(eligible, "split", sport)

    return folds, downgraded


# ═══════════════════════════════════════════════════════════════════════════════
# Fold Evaluation
# ═══════════════════════════════════════════════════════════════════════════════

def _evaluate_fold(test_games, weights, sport, team_state, games_by_date,
                   insufficient_data=False):
    """
    Score each test game with derived weights and evaluate correctness.
    Returns fold metrics dict with Wilson CIs on all accuracy metrics.
    """
    predictions = []
    total_correct = 0
    total_scored = 0

    for game in test_games:
        home = game["home_team"]
        away = game["away_team"]
        home_st = _get_state(team_state, home)
        away_st = _get_state(team_state, away)

        ctx = _build_game_context(game, home_st, away_st, games_by_date, sport)
        if ctx is None:
            _update_team_state(game, home_st, away_st)
            continue

        lean_team = _determine_lean_from_weights(weights, ctx["slot_type"],
                                                  home, away, ctx["closing_spread"])
        if lean_team is None:
            _update_team_state(game, home_st, away_st)
            continue

        lean_is_home = (lean_team == home)
        score, breakdown = _score_game_with_weights(ctx, weights, lean_is_home)
        rec = _get_rec_from_weights(score, ctx["slot_type"], weights)

        actual_covered = ctx["home_covered"]
        correct = (actual_covered == 1) if lean_is_home else (actual_covered == 0)

        total_scored += 1
        if correct:
            total_correct += 1

        predictions.append({
            "date": ctx["game_date"][:10],
            "home_team": home,
            "away_team": away,
            "lean_team": lean_team,
            "slot_type": ctx["slot_type"],
            "score": score,
            "recommendation": rec,
            "correct": correct,
            "spread": ctx["closing_spread"],
        })

        # Cap predictions in memory
        if len(predictions) > _MAX_PREDICTIONS_IN_MEMORY * 2:
            predictions = predictions[-_MAX_PREDICTIONS_IN_MEMORY:]

        _update_team_state(game, home_st, away_st)

    # Compute fold metrics
    accuracy = round(total_correct / total_scored * 100, 2) if total_scored > 0 else 0

    # ROI for qualified bets (score >= lean threshold)
    lean_thresh = weights["thresholds"]["lean"]
    strong_thresh = weights["thresholds"]["strong"]

    qualified = [p for p in predictions if p["score"] >= lean_thresh]
    q_count = len(qualified)
    if q_count > 0:
        q_correct = sum(1 for p in qualified if p["correct"])
        q_accuracy = round(q_correct / q_count * 100, 2)
        wagered = q_count
        returned = sum((1 + 100 / 110) if p["correct"] else 0 for p in qualified)
        q_roi = round((returned - wagered) / wagered * 100, 2)
    else:
        q_accuracy = 0
        q_roi = 0

    # Strong play metrics
    strong = [p for p in predictions if p["score"] >= strong_thresh]
    s_count = len(strong)
    if s_count > 0:
        s_correct = sum(1 for p in strong if p["correct"])
        s_accuracy = round(s_correct / s_count * 100, 2)
        s_wagered = s_count
        s_returned = sum((1 + 100 / 110) if p["correct"] else 0 for p in strong)
        s_roi = round((s_returned - s_wagered) / s_wagered * 100, 2)
    else:
        s_accuracy = 0
        s_roi = 0

    # Overall ROI (all scored games)
    if total_scored > 0:
        all_wagered = total_scored
        all_returned = sum((1 + 100 / 110) if p["correct"] else 0 for p in predictions)
        overall_roi = round((all_returned - all_wagered) / all_wagered * 100, 2)
    else:
        overall_roi = 0

    # Threshold analysis
    threshold_analysis = {}
    for threshold in [5, 10, 15, 20, 25]:
        tq = [p for p in predictions if p["score"] >= threshold]
        t_count = len(tq)
        if t_count > 0:
            t_correct = sum(1 for p in tq if p["correct"])
            t_accuracy = round(t_correct / t_count * 100, 2)
            t_returned = sum((1 + 100 / 110) if p["correct"] else 0 for p in tq)
            t_roi = round((t_returned - t_count) / t_count * 100, 2)
        else:
            t_accuracy = 0
            t_roi = 0
        threshold_analysis[str(threshold)] = {
            "threshold": threshold,
            "bet_count": t_count,
            "accuracy": t_accuracy,
            "roi": t_roi,
        }

    result = {
        "accuracy": accuracy,
        "roi": overall_roi,
        "total_scored": total_scored,
        "total_correct": total_correct,
        "qualified_bets": q_count,
        "qualified_accuracy": q_accuracy,
        "qualified_roi": q_roi,
        "qualified_correct": q_correct if q_count > 0 else 0,
        "strong_bets": s_count,
        "strong_accuracy": s_accuracy,
        "strong_roi": s_roi,
        "strong_correct": s_correct if s_count > 0 else 0,
        "threshold_analysis": threshold_analysis,
        "predictions": predictions[-_MAX_PREDICTIONS_IN_MEMORY:],
        "derived_thresholds": weights["thresholds"],
    }

    result["confidence_intervals"] = {
        "accuracy_ci": metric_with_ci(total_correct, total_scored, min_sample=MIN_SAMPLES["overall"]),
        "qualified_accuracy_ci": (
            metric_with_ci(q_correct, q_count, min_sample=MIN_SAMPLES["tier"])
            if q_count > 0 else metric_with_ci(0, 0)
        ),
        "strong_accuracy_ci": (
            metric_with_ci(s_correct, s_count, min_sample=MIN_SAMPLES["tier"])
            if s_count > 0 else metric_with_ci(0, 0)
        ),
    }

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics Aggregation
# ═══════════════════════════════════════════════════════════════════════════════

def _aggregate_folds(fold_results, insufficient_data=False):
    """Aggregate metrics across all folds."""
    if not fold_results:
        return {}

    n = len(fold_results)
    metrics_list = [f["metrics"] for f in fold_results]

    def _mean(values):
        if not values:
            return 0
        return round(sum(values) / len(values), 2)

    def _std(values):
        if len(values) < 2:
            return 0
        m = sum(values) / len(values)
        variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
        return round(variance ** 0.5, 2)

    accuracies = [m["accuracy"] for m in metrics_list]
    rois = [m["roi"] for m in metrics_list]
    q_accuracies = [m["qualified_accuracy"] for m in metrics_list if m["qualified_bets"] > 0]
    q_rois = [m["qualified_roi"] for m in metrics_list if m["qualified_bets"] > 0]
    s_accuracies = [m["strong_accuracy"] for m in metrics_list if m["strong_bets"] > 0]
    s_rois = [m["strong_roi"] for m in metrics_list if m["strong_bets"] > 0]

    total_test_games = sum(m["total_scored"] for m in metrics_list)
    total_qualified = sum(m["qualified_bets"] for m in metrics_list)
    total_strong = sum(m["strong_bets"] for m in metrics_list)

    # Average factor lifts across folds
    averaged_factor_lifts = {}
    all_weight_snapshots = [f["weights_snapshot"] for f in fold_results]
    if all_weight_snapshots:
        all_factor_keys = set()
        for ws in all_weight_snapshots:
            all_factor_keys.update(ws.get("factor_weights", {}).keys())
        for key in all_factor_keys:
            vals = [ws.get("factor_weights", {}).get(key, 0) for ws in all_weight_snapshots]
            averaged_factor_lifts[key] = _mean(vals)

    # Aggregate threshold analysis
    aggregated_thresholds = {}
    for threshold in ["5", "10", "15", "20", "25"]:
        bets = []
        accs = []
        rois_t = []
        for m in metrics_list:
            ta = m.get("threshold_analysis", {}).get(threshold, {})
            if ta.get("bet_count", 0) > 0:
                bets.append(ta["bet_count"])
                accs.append(ta["accuracy"])
                rois_t.append(ta["roi"])
        aggregated_thresholds[threshold] = {
            "threshold": int(threshold),
            "mean_bet_count": _mean(bets),
            "mean_accuracy": _mean(accs),
            "mean_roi": _mean(rois_t),
        }

    # Collect last predictions from final fold
    last_predictions = metrics_list[-1].get("predictions", [])[-_MAX_PREDICTIONS_IN_MEMORY:]

    # Pooled Wilson CIs across all folds
    pooled_scored = sum(m["total_scored"] for m in metrics_list)
    pooled_correct = sum(m["total_correct"] for m in metrics_list)
    pooled_q_correct = sum(m.get("qualified_correct", 0) for m in metrics_list)
    pooled_s_correct = sum(m.get("strong_correct", 0) for m in metrics_list)
    confidence_intervals = {
        "accuracy_ci": metric_with_ci(pooled_correct, pooled_scored, min_sample=MIN_SAMPLES["overall"]),
        "qualified_accuracy_ci": (
            metric_with_ci(pooled_q_correct, total_qualified, min_sample=MIN_SAMPLES["tier"])
            if total_qualified > 0 else metric_with_ci(0, 0)
        ),
        "strong_accuracy_ci": (
            metric_with_ci(pooled_s_correct, total_strong, min_sample=MIN_SAMPLES["tier"])
            if total_strong > 0 else metric_with_ci(0, 0)
        ),
    }

    return {
        "mean_accuracy": _mean(accuracies),
        "std_accuracy": _std(accuracies),
        "mean_roi": _mean(rois),
        "std_roi": _std(rois),
        "mean_qualified_accuracy": _mean(q_accuracies),
        "std_qualified_accuracy": _std(q_accuracies),
        "mean_qualified_roi": _mean(q_rois),
        "std_qualified_roi": _std(q_rois),
        "mean_qualified_bets": _mean([m["qualified_bets"] for m in metrics_list]),
        "mean_strong_accuracy": _mean(s_accuracies),
        "std_strong_accuracy": _std(s_accuracies),
        "mean_strong_roi": _mean(s_rois),
        "std_strong_roi": _std(s_rois),
        "total_test_games": total_test_games,
        "total_qualified": total_qualified,
        "total_strong": total_strong,
        "num_folds": n,
        "fold_details": [{
            "fold_idx": f["fold_idx"],
            "train_size": f["train_size"],
            "test_size": f["test_size"],
            "accuracy": f["metrics"]["accuracy"],
            "roi": f["metrics"]["roi"],
            "qualified_accuracy": f["metrics"]["qualified_accuracy"],
            "qualified_roi": f["metrics"]["qualified_roi"],
            "strong_accuracy": f["metrics"]["strong_accuracy"],
            "strong_roi": f["metrics"]["strong_roi"],
            "qualified_bets": f["metrics"]["qualified_bets"],
            "strong_bets": f["metrics"]["strong_bets"],
            "derived_thresholds": f["metrics"].get("derived_thresholds", {}),
        } for f in fold_results],
        "averaged_factor_lifts": averaged_factor_lifts,
        "threshold_analysis": aggregated_thresholds,
        "last_predictions": last_predictions,
        "insufficient_data": insufficient_data,
        "confidence_intervals": confidence_intervals,
    }


def _build_comparison(sport, wf_metrics):
    """Fetch in-sample metrics for comparison with out-of-sample."""
    in_sample = tm_db.get_latest_model_run(sport, "rules_backtest")

    comparison = {
        "in_sample": None,
        "out_of_sample": {
            "accuracy": wf_metrics.get("mean_accuracy"),
            "roi": wf_metrics.get("mean_roi"),
            "qualified_accuracy": wf_metrics.get("mean_qualified_accuracy"),
            "qualified_roi": wf_metrics.get("mean_qualified_roi"),
            "strong_accuracy": wf_metrics.get("mean_strong_accuracy"),
            "strong_roi": wf_metrics.get("mean_strong_roi"),
        },
        "overfit_gap": None,
    }

    if in_sample:
        in_acc = in_sample.get("accuracy", 0) or 0
        comparison["in_sample"] = {
            "accuracy": in_acc,
            "roi": in_sample.get("roi", 0),
            "total_predictions": in_sample.get("total_predictions", 0),
        }
        out_acc = wf_metrics.get("mean_accuracy", 0) or 0
        comparison["overfit_gap"] = round(in_acc - out_acc, 2)

    return comparison


# ═══════════════════════════════════════════════════════════════════════════════
# Utility Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _build_data_warning(total, insufficient_data, weight_tuning_locked):
    """Build human-readable warning message for small-sample sports."""
    if not insufficient_data:
        return None

    parts = [
        f"INSUFFICIENT DATA FOR VALIDATION: Only {total} games available "
        f"(minimum {MIN_GAMES_RELIABLE} recommended).",
        "Results are UNRELIABLE — confidence intervals are wide.",
        "All accuracy metrics include Wilson score 95% confidence intervals.",
    ]
    if weight_tuning_locked:
        parts.append(
            f"Weight tuning LOCKED — using production weights (need "
            f"{MIN_GAMES_WEIGHT_TUNING}+ games to derive weights from data)."
        )
    return " ".join(parts)


def _get_fallback_weights(sport):
    """
    Returns production-equivalent weights when weight tuning is locked
    (< 300 games). Built from UNIVERSAL_DEFAULTS + only validated overrides
    from the registry, ensuring unproven sport-specific tweaks don't
    contaminate the fallback.
    """
    defaults = UNIVERSAL_DEFAULTS

    # Base factor weights from universal defaults
    base_factors = {
        "slot_public": 0,
        "line_movement": 0,
        "rank_scam": 5,
        "spread_discrepancy": 5,
        "trend_discrepancy": 5,
        "ou_discrepancy": 5,
        "vegas_trap": 5,
        "b2b_bonus": defaults["b2b_bonus"],
        "b2b_penalty": defaults["b2b_penalty"],
        "ats_bonus": defaults["ats_bonus"],
        "ats_penalty": defaults["ats_penalty"],
        "home_away_split": defaults["home_away_split"],
        "h2h_revenge": defaults["h2h_revenge"],
        "h2h_dominance": defaults["h2h_dominance"],
    }

    # Start from universal defaults
    weights = {
        "lean": defaults["lean"],
        "lean_public": defaults["lean_public"],
        "lean_vegas": defaults["lean_vegas"],
        "weak_lean": False,
        "public_slot_bonus": defaults["public_slot_bonus"],
        "day_penalties": dict(defaults["day_penalties"]),
        "spread_buckets": dict(defaults["spread_buckets"]),
        "factor_weights": dict(base_factors),
        "line_toward_dog": defaults["line_toward_dog"],
        "line_toward_fav": defaults["line_toward_fav"],
        "line_movement_tiers": {"1-2": 3, "2-3": 5, "3+": 8},
        "thresholds": {"lean": 5, "strong": 15},  # conservative defaults
    }

    # Apply only validated overrides from the registry
    lean_override = get_override(sport, "lean_direction", None)
    if lean_override == "always_underdog":
        weights["lean"] = "always_underdog"
        weights["lean_public"] = "underdog"
        weights["lean_vegas"] = "underdog"
    elif lean_override == "flipped":
        weights["lean"] = "slot_dependent"
        weights["lean_public"] = "underdog"
        weights["lean_vegas"] = "favorite"

    # Public slot bonus
    weights["public_slot_bonus"] = get_override(
        sport, "public_slot_bonus", defaults["public_slot_bonus"])

    # Line direction
    weights["line_toward_dog"] = get_override(
        sport, "line_toward_dog", defaults["line_toward_dog"])
    weights["line_toward_fav"] = get_override(
        sport, "line_toward_fav", defaults["line_toward_fav"])

    # Factor weight overrides (only validated)
    for key in ("b2b_bonus", "b2b_penalty", "ats_bonus", "ats_penalty",
                "home_away_split", "h2h_revenge", "h2h_dominance"):
        weights["factor_weights"][key] = get_override(
            sport, key, defaults.get(key, base_factors.get(key, 0)))

    # Day penalties (only validated)
    _day_penalty_map = {
        "nba": {"tuesday": "tuesday_penalty"},
        "cbb": {"sunday": "sunday_penalty"},
        "nhl": {"friday": "friday_penalty"},
    }
    for day, override_name in _day_penalty_map.get(sport, {}).items():
        val = get_override(sport, override_name, 0)
        if val != 0:
            weights["day_penalties"][day] = val

    # Spread bucket overrides (only validated)
    _spread_override_map = {
        "nba": [
            ("3-5", "spread_3_5_bonus"),
            ("5-7", "spread_5_7_penalty"),
            ("13-100", "spread_13_plus_penalty"),
        ],
        "cbb": [
            ("5-7", "spread_6_10_bonus"),     # maps to 6-10 in scoring
            ("7-10", "spread_6_10_bonus"),
            ("0-3", "spread_0_3_penalty"),
            ("13-100", "spread_15_plus_penalty"),
        ],
        "nfl": [
            ("3-5", "spread_3_7_bonus"),
            ("5-7", "spread_3_7_bonus"),
            ("0-3", "spread_0_3_penalty"),
            ("10-13", "spread_10_plus_penalty"),
            ("13-100", "spread_10_plus_penalty"),
        ],
    }
    for bucket_key, override_name in _spread_override_map.get(sport, []):
        val = get_override(sport, override_name, 0)
        if val != 0:
            weights["spread_buckets"][bucket_key] = val

    # Sport-specific threshold defaults
    _threshold_defaults = {
        "nba": {"lean": 5, "strong": 10},
        "nhl": {"lean": 3, "strong": 8},
        "cbb": {"lean": 10, "strong": 13},
        "nfl": {"lean": 10, "strong": 20},
        "cfb": {"lean": 12, "strong": 15},
    }
    weights["thresholds"] = _threshold_defaults.get(sport, {"lean": 5, "strong": 15})

    # Sport-specific line movement tiers
    if sport == "nba":
        weights["line_movement_tiers"] = {"1-2": 2, "2-3": 3, "3+": 5}

    return weights


def _safe_rate(data):
    """Calculate rate from a dict with dog_cover and total."""
    if data["total"] == 0:
        return 50.0
    return round(data["dog_cover"] / data["total"] * 100, 2)


def _safe_rate_simple(data):
    """Calculate rate from a dict with correct and total."""
    if data["total"] == 0:
        return 50.0
    return round(data["correct"] / data["total"] * 100, 2)


def _track_factor(tracker, factor_name, fired, correct):
    if fired:
        tracker[factor_name]["fired"] += 1
        if correct:
            tracker[factor_name]["correct_when_fired"] += 1
    else:
        tracker[factor_name]["not_fired"] += 1
        if correct:
            tracker[factor_name]["correct_when_not_fired"] += 1


def _resolve_b2b(ctx, lean_is_home):
    """Resolve B2B bonus/penalty based on lean direction."""
    if lean_is_home:
        lean_b2b = ctx["lean_b2b_home"]
        opp_b2b = ctx["lean_b2b_away"]
    else:
        lean_b2b = ctx["lean_b2b_away"]
        opp_b2b = ctx["lean_b2b_home"]

    bonus = opp_b2b and not lean_b2b
    penalty = lean_b2b and not opp_b2b
    return bonus, penalty


def _resolve_h2h(ctx, lean_is_home):
    """Resolve H2H revenge/dominance based on lean direction."""
    if lean_is_home:
        h2h_margin = ctx["h2h_margin_home"]
    else:
        h2h_margin = ctx["h2h_margin_away"]

    threshold = ctx["h2h_threshold"]
    revenge = False
    dominance = False
    if h2h_margin is not None:
        if h2h_margin < 0 and abs(h2h_margin) >= threshold:
            revenge = True
        elif h2h_margin > 0 and h2h_margin >= threshold:
            dominance = True
    return revenge, dominance


def _resolve_ats(ctx, lean_is_home):
    """Resolve ATS bonus/penalty based on lean direction."""
    if lean_is_home:
        return ctx["ats_bonus_home"], ctx["ats_penalty_home"]
    else:
        return ctx["ats_bonus_away"], ctx["ats_penalty_away"]


def _snapshot_weights(weights):
    """Create a JSON-safe snapshot of derived weights."""
    return {
        "lean": weights["lean"],
        "lean_public": weights["lean_public"],
        "lean_vegas": weights["lean_vegas"],
        "weak_lean": weights.get("weak_lean", False),
        "public_slot_bonus": weights["public_slot_bonus"],
        "day_penalties": dict(weights["day_penalties"]),
        "spread_buckets": dict(weights["spread_buckets"]),
        "factor_weights": dict(weights["factor_weights"]),
        "line_toward_dog": weights["line_toward_dog"],
        "line_toward_fav": weights["line_toward_fav"],
        "line_movement_tiers": dict(weights["line_movement_tiers"]),
        "thresholds": dict(weights["thresholds"]),
    }
