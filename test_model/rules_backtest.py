"""
Test Model Rules Backtest — replays the actual game_scanner.py scoring weights
against historical outcomes to validate the rules-based system.

Imports and calls the same functions used in production (classify_slot,
detect_movement, confirms_slot, score_line_movement, _determine_lean,
_calculate_score, _analyze_home_away_split, _detect_rank_scam,
_detect_spread_discrepancy) so results reflect the real scoring system.

Factors NOT replayable (set to 0, documented):
  - Trell Rule (+5): NOW partially replayable via historical injury backfill
  - Public betting (+3/+5): requires Pinnacle odds
  - Feedback loop (-2/+3): requires tracker ledger
  - NFL weather (+5): requires weather API at game time
"""

import threading
from datetime import datetime, timedelta
from collections import defaultdict

from time_slots import classify_slot
from line_movement import detect_movement, confirms_slot, score_line_movement
from rank_analysis import _detect_rank_scam, _detect_spread_discrepancy
from constants import get_recommendation, wilson_interval, metric_with_ci, MIN_SAMPLES
from analysis_factors import (
    _determine_lean, _calculate_score, _analyze_home_away_split,
    H2H_REVENGE_THRESHOLDS,
)
from calibration import compute_calibration
from factor_analysis import run_factor_analysis
from test_model import db as tm_db
from test_model.date_utils import parse_iso_date, parse_game_dt

MIN_WARMUP_GAMES = 10  # Need some team_state history before scoring

MISSING_FACTORS = [
    "Trell Rule (+5): partially replayable via injury backfill (if data exists)",
    "Public betting (+3/+5): requires Pinnacle odds at game time",
    "Feedback loop (-2/+3): requires tracker ledger at game time",
    "NFL weather (+5): requires weather API at game time",
]

# Progress dict for polling
_rules_progress = {}
_rules_lock = threading.Lock()


def get_rules_backtest_status(sport):
    with _rules_lock:
        return dict(_rules_progress.get(sport, {}))


def _parse_game_dt(game_date_str, sport):
    """Parse game_date ISO string to timezone-adjusted datetime for classification."""
    return parse_game_dt(game_date_str, sport)


def _group_games_by_date(games):
    """Group games by calendar date string (YYYY-MM-DD) for slate context."""
    by_date = defaultdict(list)
    for game in games:
        gd = game.get("game_date", "")
        if gd:
            date_key = gd[:10]  # "2024-01-15T..." -> "2024-01-15"
        else:
            date_key = "unknown"
        by_date[date_key].append(game)
    # Sort each date's games by game_date
    for dk in by_date:
        by_date[dk].sort(key=lambda g: g.get("game_date", ""))
    return by_date


def run_rules_backtest(sport):
    """
    Replay the rules-based scoring system against historical outcomes.
    Runs synchronously. Call via start_rules_backtest_thread() for background.
    """
    games = tm_db.get_historical_games(sport)
    if not games:
        with _rules_lock:
            _rules_progress[sport] = {
                "status": "error",
                "message": "No historical games found.",
            }
        return

    # Filter to final games with spread and definitive outcome
    eligible = [
        g for g in games
        if g.get("closing_spread") is not None
        and g.get("home_covered") in (0, 1)
        and g.get("game_status") == "STATUS_FINAL"
    ]
    del games  # Free raw games list

    if len(eligible) < MIN_WARMUP_GAMES + 5:
        with _rules_lock:
            _rules_progress[sport] = {
                "status": "error",
                "message": f"Need at least {MIN_WARMUP_GAMES + 5} eligible games, have {len(eligible)}. Collect more data first.",
            }
        return

    total = len(eligible)
    with _rules_lock:
        _rules_progress[sport] = {
            "status": "running",
            "total_games": total,
            "processed": 0,
            "current_date": "",
        }

    # Build team_state chronologically
    team_state = {}

    def _get_state(team):
        if team not in team_state:
            team_state[team] = {
                "dates": [],
                "results": [],       # 1=win, 0=loss
                "scores": [],
                "opp_scores": [],
                "opponents": [],     # opponent name per game
                "margins": [],       # score margin per game
                "ats_covers": 0,
                "ats_total": 0,
            }
        return team_state[team]

    # Group for slate context
    games_by_date = _group_games_by_date(eligible)

    # Predictions and factor tracking
    # Only keep last 200 predictions in memory (rest are counted in trackers)
    predictions = []
    _MAX_PREDICTIONS_IN_MEMORY = 200
    # Lightweight pairs for calibration (never truncated — ~8 bytes each)
    calibration_pairs = []
    # Per-game factor records for factor analysis (never truncated)
    factor_records = []
    factor_tracker = defaultdict(lambda: {"fired": 0, "correct_when_fired": 0,
                                           "correct_when_not_fired": 0,
                                           "not_fired": 0})
    slot_tracker = defaultdict(lambda: {"total": 0, "correct": 0})
    rec_tracker = defaultdict(lambda: {"total": 0, "correct": 0})
    day_tracker = defaultdict(lambda: {"total": 0, "correct": 0})
    processed = 0

    for game in eligible:
        home = game["home_team"]
        away = game["away_team"]
        home_st = _get_state(home)
        away_st = _get_state(away)
        game_date_str = game.get("game_date", "")

        # Skip warmup period
        total_team_games = len(home_st["dates"]) + len(away_st["dates"])
        if processed < MIN_WARMUP_GAMES:
            # Still in warmup — update state but don't score
            _update_team_state(game, home_st, away_st)
            processed += 1
            with _rules_lock:
                _rules_progress[sport]["processed"] = processed
            continue

        with _rules_lock:
            _rules_progress[sport]["current_date"] = game_date_str[:10]

        # ── Classify slot ──
        local_dt = _parse_game_dt(game_date_str, sport)
        if local_dt is None:
            _update_team_state(game, home_st, away_st)
            processed += 1
            with _rules_lock:
                _rules_progress[sport]["processed"] = processed
            continue

        day_of_week = local_dt.strftime("%A")
        hour, minute = local_dt.hour, local_dt.minute

        # Get date key for slate context
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
                dg_dt = _parse_game_dt(dg.get("game_date", ""), sport)
                if dg_dt:
                    dg_mins = dg_dt.hour * 60 + dg_dt.minute
                    if abs(dg_mins - snf_mins) > 30:
                        if dg.get("event_id") == game.get("event_id"):
                            is_last_sunday_game = True
                        break

        # Classify
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
            from time_slots import first_game_slot_override
            if is_first_game:
                slot_type = first_game_slot_override(day_of_week)
            else:
                slot_type = classify_slot(day_of_week, hour, minute)

        # Skip skip-slot games
        if slot_type == "skip":
            _update_team_state(game, home_st, away_st)
            processed += 1
            with _rules_lock:
                _rules_progress[sport]["processed"] = processed
            continue

        closing_spread = game["closing_spread"]
        opening_spread = game.get("opening_spread")
        home_rank = game.get("home_rank")
        away_rank = game.get("away_rank")
        over_under = game.get("over_under")

        # ── Line movement ──
        line_confirms = False
        line_magnitude = 0.0
        line_toward_dog = False
        line_toward_fav = False
        if opening_spread is not None and closing_spread is not None:
            movement, line_magnitude = detect_movement(opening_spread, closing_spread)
            line_confirms = confirms_slot(movement, slot_type)
            # NBA V5: raw line direction toward dog/fav
            raw_movement = closing_spread - opening_spread
            if closing_spread < 0:  # home favored
                line_toward_dog = raw_movement > 0.5
                line_toward_fav = raw_movement < -0.5
            else:  # away favored
                line_toward_dog = raw_movement < -0.5
                line_toward_fav = raw_movement > 0.5

        # ── Determine lean ──
        lean_team = _determine_lean(slot_type, home, away, closing_spread, sport=sport)
        if lean_team is None:
            _update_team_state(game, home_st, away_st)
            processed += 1
            with _rules_lock:
                _rules_progress[sport]["processed"] = processed
            continue

        # ── Rank analysis (CFB/CBB only) ──
        rank_scam_applies = False
        spread_disc_applies = False
        if sport in ("cfb", "cbb"):
            rank_scam = _detect_rank_scam(home_rank, away_rank, closing_spread, slot_type)
            spread_disc = _detect_spread_discrepancy(home_rank, away_rank, closing_spread, slot_type, sport=sport)
            rank_scam_applies = rank_scam.get("is_rank_scam", False)
            spread_disc_applies = spread_disc.get("is_discrepancy", False)

        # ── Home/away split ──
        home_away_applies = _analyze_home_away_split(lean_team, home, slot_type, closing_spread)

        # ── B2B detection (from team_state dates) ──
        b2b_bonus = False
        b2b_penalty = False
        if sport in ("nba", "nhl"):
            lean_is_home = (lean_team == home)
            lean_st = home_st if lean_is_home else away_st
            opp_st = away_st if lean_is_home else home_st

            lean_b2b = _is_b2b_from_state(lean_st, game_date_str)
            opp_b2b = _is_b2b_from_state(opp_st, game_date_str)

            if opp_b2b and not lean_b2b:
                b2b_bonus = True
            elif lean_b2b and not opp_b2b:
                b2b_penalty = True

        # ── H2H revenge/dominance (from team_state opponents) ──
        h2h_revenge = False
        h2h_dominance = False
        if lean_team:
            lean_is_home = (lean_team == home)
            lean_st = home_st if lean_is_home else away_st
            opp_name = away if lean_is_home else home
            threshold = H2H_REVENGE_THRESHOLDS.get(sport, 10)
            h2h_margin = _find_last_h2h_margin(lean_st, opp_name)
            if h2h_margin is not None:
                if h2h_margin < 0 and abs(h2h_margin) >= threshold:
                    h2h_revenge = True
                elif h2h_margin > 0 and h2h_margin >= threshold:
                    h2h_dominance = True

        # ── Vegas trap (NBA only) ──
        vegas_trap_bonus = 0
        if sport == "nba" and slot_type in ("vegas", "trap") and abs(closing_spread) >= 7:
            # Identify favorite
            if closing_spread < 0:
                fav_st = home_st
            else:
                fav_st = away_st
            fav_wins_7 = sum(fav_st["results"][-7:]) if len(fav_st["results"]) >= 5 else None
            if fav_wins_7 is not None and fav_wins_7 <= 2:
                vegas_trap_bonus = 5
                # Check if underdog also cold
                if closing_spread < 0:
                    dog_st = away_st
                else:
                    dog_st = home_st
                dog_wins_7 = sum(dog_st["results"][-7:]) if len(dog_st["results"]) >= 5 else None
                if dog_wins_7 is not None and dog_wins_7 <= 2:
                    vegas_trap_bonus = 7

        # ── NFL trend discrepancy (from team_state) ──
        trend_disc_applies = False
        if sport == "nfl" and slot_type == "vegas":
            trend_disc_applies = _check_nfl_trend_from_state(home_st, away_st)

        # ── NFL O/U discrepancy (from team_state + over_under) ──
        ou_disc_applies = False
        if sport == "nfl" and slot_type == "vegas" and over_under is not None:
            ou_disc_applies = _check_nfl_ou_from_state(home_st, away_st, over_under)

        # ── ATS record (from in-replay cover outcomes) ──
        ats_bonus = False
        ats_penalty = False
        if lean_team:
            lean_st_for_ats = home_st if lean_team == home else away_st
            if lean_st_for_ats["ats_total"] >= MIN_SAMPLES["ats"]:
                ats_rate = lean_st_for_ats["ats_covers"] / lean_st_for_ats["ats_total"] * 100
                if ats_rate > 60:
                    ats_bonus = True
                elif ats_rate < 40:
                    ats_penalty = True

        # ── Trell Rule (from historical injury backfill if available) ──
        trell_applies = False
        try:
            injuries = tm_db.get_historical_injuries(sport, game_date_str)
            if injuries and lean_team:
                # Trell fires if a star on the OPPOSING team is out
                opp_team = away if lean_team == home else home
                for inj in injuries:
                    if inj.get("is_star") and inj.get("team") == opp_team:
                        trell_applies = True
                        break
        except Exception:
            pass  # Graceful: if no data, keep False

        # ── Calculate score ──
        score, breakdown = _calculate_score(
            slot_type, line_confirms, trell_applies,
            line_magnitude=line_magnitude,
            rank_scam_applies=rank_scam_applies,
            spread_disc_applies=spread_disc_applies,
            trend_disc_applies=trend_disc_applies,
            ou_disc_applies=ou_disc_applies,
            weather_applies=False,   # not replayable
            spread_value=closing_spread,
            sport=sport,
            b2b_bonus=b2b_bonus,
            b2b_penalty=b2b_penalty,
            ats_bonus=ats_bonus,
            ats_penalty=ats_penalty,
            home_away_applies=home_away_applies,
            public_betting_bonus=0,  # not replayable
            feedback_adjustment=0,   # not replayable
            h2h_revenge_bonus=h2h_revenge,
            h2h_dominance_bonus=h2h_dominance,
            vegas_trap_bonus=vegas_trap_bonus,
            line_toward_dog=line_toward_dog,
            line_toward_fav=line_toward_fav,
            day_of_week=day_of_week,
        )

        # ── Recommendation ──
        recommendation = get_recommendation(score, slot_type, sport)

        # ── Evaluate correctness ──
        # lean_team covers = correct prediction
        actual_covered = game["home_covered"]  # 1 = home covered
        lean_is_home = (lean_team == home)
        if lean_is_home:
            correct = (actual_covered == 1)
        else:
            correct = (actual_covered == 0)

        # Track factor performance
        _track_factor(factor_tracker, "slot_public", slot_type == "public", correct)
        _track_factor(factor_tracker, "line_movement", line_confirms, correct)
        _track_factor(factor_tracker, "rank_scam", rank_scam_applies, correct)
        _track_factor(factor_tracker, "spread_discrepancy", spread_disc_applies, correct)
        _track_factor(factor_tracker, "home_away_split", home_away_applies, correct)
        _track_factor(factor_tracker, "b2b_bonus", b2b_bonus, correct)
        _track_factor(factor_tracker, "b2b_penalty", b2b_penalty, correct)
        _track_factor(factor_tracker, "h2h_revenge", h2h_revenge, correct)
        _track_factor(factor_tracker, "h2h_dominance", h2h_dominance, correct)
        _track_factor(factor_tracker, "vegas_trap", vegas_trap_bonus > 0, correct)
        _track_factor(factor_tracker, "trend_discrepancy", trend_disc_applies, correct)
        _track_factor(factor_tracker, "ou_discrepancy", ou_disc_applies, correct)
        _track_factor(factor_tracker, "ats_bonus", ats_bonus, correct)
        _track_factor(factor_tracker, "ats_penalty", ats_penalty, correct)
        _track_factor(factor_tracker, "spread_penalty", breakdown.get("spread_penalty", 0) < 0, correct)
        _track_factor(factor_tracker, "line_toward_dog", line_toward_dog, correct)
        _track_factor(factor_tracker, "line_toward_fav", line_toward_fav, correct)
        _track_factor(factor_tracker, "day_penalty", breakdown.get("day_penalty", 0) < 0, correct)
        _track_factor(factor_tracker, "spread_sweet_spot", breakdown.get("spread_penalty", 0) > 0, correct)
        _track_factor(factor_tracker, "trell_rule", trell_applies, correct)

        # Per-game factor record for factor analysis (never truncated)
        factor_records.append({
            "score": score,
            "correct": correct,
            "breakdown": breakdown,
            "factors": {
                "slot_public": slot_type == "public",
                "line_movement": line_confirms,
                "rank_scam": rank_scam_applies,
                "spread_discrepancy": spread_disc_applies,
                "home_away_split": home_away_applies,
                "b2b_bonus": b2b_bonus,
                "b2b_penalty": b2b_penalty,
                "h2h_revenge": h2h_revenge,
                "h2h_dominance": h2h_dominance,
                "vegas_trap": vegas_trap_bonus > 0,
                "trend_discrepancy": trend_disc_applies,
                "ou_discrepancy": ou_disc_applies,
                "ats_bonus": ats_bonus,
                "ats_penalty": ats_penalty,
                "spread_penalty": breakdown.get("spread_penalty", 0) < 0,
                "spread_sweet_spot": breakdown.get("spread_penalty", 0) > 0,
                "line_toward_dog": line_toward_dog,
                "line_toward_fav": line_toward_fav,
                "day_penalty": breakdown.get("day_penalty", 0) < 0,
                "trell_rule": trell_applies,
            },
        })

        # Track by slot type
        slot_tracker[slot_type]["total"] += 1
        if correct:
            slot_tracker[slot_type]["correct"] += 1

        # Track by recommendation
        rec_tracker[recommendation]["total"] += 1
        if correct:
            rec_tracker[recommendation]["correct"] += 1

        # Track by day of week
        day_tracker[day_of_week]["total"] += 1
        if correct:
            day_tracker[day_of_week]["correct"] += 1

        # Lightweight calibration pair (never truncated)
        calibration_pairs.append({"score": score, "correct": correct})

        predictions.append({
            "date": game_date_str[:10],
            "home_team": home,
            "away_team": away,
            "lean_team": lean_team,
            "slot_type": slot_type,
            "score": score,
            "recommendation": recommendation,
            "correct": correct,
            "spread": closing_spread,
            "opening_spread": opening_spread,
            "breakdown": breakdown,
        })
        # Cap in-memory predictions to avoid unbounded growth
        if len(predictions) > _MAX_PREDICTIONS_IN_MEMORY * 2:
            predictions = predictions[-_MAX_PREDICTIONS_IN_MEMORY:]

        # ── Update team state AFTER scoring ──
        _update_team_state(game, home_st, away_st)

        processed += 1
        with _rules_lock:
            _rules_progress[sport]["processed"] = processed

    # ── Compute metrics ──
    scored_predictions = [p for p in predictions]  # all post-warmup
    metrics = _compute_rules_metrics(scored_predictions, factor_tracker,
                                      slot_tracker, rec_tracker, day_tracker)

    # ── Calibration analysis (uses ALL pairs, not truncated) ──
    calibration = compute_calibration(calibration_pairs, sport)
    metrics["calibration"] = calibration

    # ── Factor analysis (uses ALL factor records, not truncated) ──
    factor_health = run_factor_analysis(factor_records, sport)
    metrics["factor_health"] = factor_health

    # Save to model_runs table
    tm_db.save_model_run({
        "sport": sport,
        "run_type": "rules_backtest",
        "accuracy": metrics.get("accuracy"),
        "roi": metrics.get("roi"),
        "clv_avg": metrics.get("clv_avg"),
        "total_predictions": metrics.get("total_predictions"),
        "qualified_bets": metrics.get("qualified_bets"),
        "feature_importances": metrics.get("factor_breakdown", {}),
        "model_params": {
            "missing_factors": MISSING_FACTORS,
            "min_warmup": MIN_WARMUP_GAMES,
            "sport": sport,
            "calibration": calibration,
            "factor_health": factor_health,
        },
        "threshold_analysis": metrics.get("threshold_analysis", {}),
        "predictions": scored_predictions[-200:],
    })

    with _rules_lock:
        _rules_progress[sport] = {
            "status": "complete",
            "total_games": total,
            "processed": processed,
            "current_date": "",
            "metrics": metrics,
        }

    return metrics


def _is_b2b_from_state(team_st, game_date_str):
    """Check if team played yesterday based on state dates."""
    if not team_st["dates"]:
        return False
    last_dt = parse_iso_date(team_st["dates"][-1])
    game_dt = parse_iso_date(game_date_str)
    if last_dt is None or game_dt is None:
        return False
    return abs((game_dt - last_dt).days) <= 1


def _find_last_h2h_margin(lean_st, opp_name):
    """Find the last matchup margin against opp_name from lean team's state."""
    for i in range(len(lean_st["opponents"]) - 1, -1, -1):
        if lean_st["opponents"][i] == opp_name:
            return lean_st["margins"][i]
    return None


def _check_nfl_trend_from_state(home_st, away_st):
    """Approximate NFL trend discrepancy from team state last 4 results."""
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

    home_signal = classify_trend(home_st["results"])
    away_signal = classify_trend(away_st["results"])
    return home_signal is not None or away_signal is not None


def _check_nfl_ou_from_state(home_st, away_st, over_under):
    """Approximate NFL O/U discrepancy from team scoring averages."""
    if over_under > 50.5:
        return True

    home_avg = sum(home_st["scores"][-4:]) / max(len(home_st["scores"][-4:]), 1) if home_st["scores"] else 0
    away_avg = sum(away_st["scores"][-4:]) / max(len(away_st["scores"][-4:]), 1) if away_st["scores"] else 0
    combined = home_avg + away_avg
    return abs(over_under - combined) >= 6


_TEAM_STATE_MAX = 20  # Only need last ~4-10 games for lookups


def _update_team_state(game, home_st, away_st):
    """Record game result into both teams' state, trimmed to rolling window."""
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

    # Trim lists to rolling window to save memory
    for st in (home_st, away_st):
        for key in ("results", "scores", "opp_scores", "dates", "opponents", "margins"):
            if len(st[key]) > _TEAM_STATE_MAX:
                st[key] = st[key][-_TEAM_STATE_MAX:]

    # ATS tracking
    if home_covered == 1:
        home_st["ats_covers"] += 1
        home_st["ats_total"] += 1
        away_st["ats_total"] += 1
    elif home_covered == 0:
        away_st["ats_covers"] += 1
        home_st["ats_total"] += 1
        away_st["ats_total"] += 1


def _track_factor(tracker, factor_name, fired, correct):
    """Track factor fire rate and accuracy."""
    if fired:
        tracker[factor_name]["fired"] += 1
        if correct:
            tracker[factor_name]["correct_when_fired"] += 1
    else:
        tracker[factor_name]["not_fired"] += 1
        if correct:
            tracker[factor_name]["correct_when_not_fired"] += 1


def _compute_rules_metrics(predictions, factor_tracker, slot_tracker, rec_tracker,
                           day_tracker=None):
    """Compute comprehensive metrics for the rules replay."""
    if day_tracker is None:
        day_tracker = {}
    if not predictions:
        return {
            "accuracy": 0, "roi": 0, "clv_avg": 0,
            "total_predictions": 0, "qualified_bets": 0,
            "factor_breakdown": {}, "slot_breakdown": {},
            "rec_breakdown": {}, "day_breakdown": {},
            "threshold_analysis": {},
        }

    total = len(predictions)
    correct = sum(1 for p in predictions if p["correct"])
    accuracy = round(correct / total * 100, 2)
    accuracy_ci = metric_with_ci(correct, total, min_sample=MIN_SAMPLES["overall"])

    # ── ROI at -110 vig for different thresholds ──
    threshold_analysis = {}
    for threshold in [5, 10, 15, 20, 25]:
        qualified = [p for p in predictions if p["score"] >= threshold]
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
        threshold_analysis[str(threshold)] = {
            "threshold": threshold,
            "bet_count": q_count,
            "accuracy": q_accuracy,
            "accuracy_ci": metric_with_ci(q_correct if q_count > 0 else 0, q_count, min_sample=MIN_SAMPLES["tier"]),
            "roi": q_roi,
        }

    # Overall ROI: score >= 10 (LEAN or better)
    qualified = [p for p in predictions if p["score"] >= 10]
    qualified_count = len(qualified)
    if qualified_count > 0:
        q_wagered = qualified_count
        q_returned = sum((1 + 100 / 110) if p["correct"] else 0 for p in qualified)
        roi = round((q_returned - q_wagered) / q_wagered * 100, 2)
        clv_values = []
        for p in qualified:
            op = p.get("opening_spread")
            cl = p.get("spread")
            if op is not None and cl is not None:
                if p["lean_team"] == p["home_team"]:
                    clv_values.append(round(op - cl, 2))
                else:
                    clv_values.append(round(cl - op, 2))
        clv_avg = round(sum(clv_values) / len(clv_values), 2) if clv_values else 0
        clv_hit_rate = round(sum(1 for c in clv_values if c > 0) / len(clv_values) * 100, 1) if clv_values else 0
    else:
        roi = 0
        clv_avg = 0

    # ── Factor breakdown ──
    factor_breakdown = {}
    for factor_name, data in factor_tracker.items():
        fired = data["fired"]
        not_fired = data["not_fired"]
        if fired > 0:
            acc_when_fired = round(data["correct_when_fired"] / fired * 100, 2)
        else:
            acc_when_fired = 0
        if not_fired > 0:
            acc_when_not_fired = round(data["correct_when_not_fired"] / not_fired * 100, 2)
        else:
            acc_when_not_fired = 0
        lift = round(acc_when_fired - acc_when_not_fired, 2) if fired > 0 and not_fired > 0 else 0
        factor_breakdown[factor_name] = {
            "fired": fired,
            "accuracy_when_fired": acc_when_fired,
            "accuracy_when_fired_ci": metric_with_ci(data["correct_when_fired"], fired, min_sample=MIN_SAMPLES["factor"]),
            "accuracy_when_not_fired": acc_when_not_fired,
            "lift": lift,
        }

    # ── Slot breakdown ──
    slot_breakdown = {}
    for slot_type, data in slot_tracker.items():
        if data["total"] > 0:
            slot_breakdown[slot_type] = {
                "total": data["total"],
                "correct": data["correct"],
                "accuracy": round(data["correct"] / data["total"] * 100, 2),
                "accuracy_ci": metric_with_ci(data["correct"], data["total"], min_sample=MIN_SAMPLES["slot"]),
            }

    # ── Recommendation breakdown ──
    rec_breakdown = {}
    for rec, data in rec_tracker.items():
        if data["total"] > 0:
            rec_breakdown[rec] = {
                "total": data["total"],
                "correct": data["correct"],
                "accuracy": round(data["correct"] / data["total"] * 100, 2),
                "accuracy_ci": metric_with_ci(data["correct"], data["total"], min_sample=MIN_SAMPLES["tier"]),
            }

    # ── Day-of-week breakdown ──
    day_breakdown = {}
    for day_name, data in day_tracker.items():
        if data["total"] > 0:
            day_breakdown[day_name] = {
                "total": data["total"],
                "correct": data["correct"],
                "accuracy": round(data["correct"] / data["total"] * 100, 2),
                "accuracy_ci": metric_with_ci(data["correct"], data["total"], min_sample=MIN_SAMPLES["day"]),
            }

    # ── CLV by tier ──
    clv_by_tier = []
    for tier in ["STRONG PLAY", "CONFIDENT", "LEAN"]:
        tier_preds = [p for p in qualified if p.get("recommendation") == tier]
        tier_clvs = []
        for p in tier_preds:
            op = p.get("opening_spread")
            cl = p.get("spread")
            if op is not None and cl is not None:
                if p["lean_team"] == p["home_team"]:
                    tier_clvs.append(round(op - cl, 2))
                else:
                    tier_clvs.append(round(cl - op, 2))
        if tier_clvs:
            clv_by_tier.append({
                "tier": tier,
                "avg_clv": round(sum(tier_clvs) / len(tier_clvs), 2),
                "clv_hit_rate": round(sum(1 for c in tier_clvs if c > 0) / len(tier_clvs) * 100, 1),
                "count": len(tier_clvs),
            })

    return {
        "accuracy": accuracy,
        "accuracy_ci": accuracy_ci,
        "roi": roi,
        "clv_avg": clv_avg,
        "clv_hit_rate": clv_hit_rate,
        "clv_count": len(clv_values),
        "clv_by_tier": clv_by_tier,
        "total_predictions": total,
        "qualified_bets": qualified_count,
        "factor_breakdown": factor_breakdown,
        "slot_breakdown": slot_breakdown,
        "rec_breakdown": rec_breakdown,
        "day_breakdown": day_breakdown,
        "threshold_analysis": threshold_analysis,
    }


def start_rules_backtest_thread(sport):
    """Start rules backtest in a background thread. Returns immediately."""
    with _rules_lock:
        existing = _rules_progress.get(sport, {})
        if existing.get("status") == "running":
            return False

    target_fn = run_soccer_backtest if sport == "soccer" else run_rules_backtest
    t = threading.Thread(target=target_fn, args=(sport,), daemon=True)
    t.start()
    return True


# ─── Soccer Three-Way Backtest ───────────────────────────────────────────

def run_soccer_backtest(sport="soccer"):
    """
    Backtest soccer 1X2 predictions using the SoccerEVModel.
    Three-way outcome: home_win (0), draw (1), away_win (2).
    """
    games = tm_db.get_historical_games(sport)
    if not games:
        with _rules_lock:
            _rules_progress[sport] = {
                "status": "error",
                "message": "No historical soccer games found.",
            }
        return

    eligible = [
        g for g in games
        if g.get("game_status") == "STATUS_FINAL"
        and g.get("home_score") is not None
        and g.get("away_score") is not None
    ]
    del games

    if len(eligible) < 50:
        with _rules_lock:
            _rules_progress[sport] = {
                "status": "error",
                "message": f"Need at least 50 eligible games, have {len(eligible)}.",
            }
        return

    total = len(eligible)
    with _rules_lock:
        _rules_progress[sport] = {
            "status": "running",
            "total_games": total,
            "processed": 0,
            "current_date": "",
        }

    # Build team state for xG proxies
    _LEAGUE_AVG_XG = 1.35
    _PRIOR = 10
    team_state = {}

    def _get_st(team):
        if team not in team_state:
            team_state[team] = {"gf": [], "ga": [], "results": []}
        return team_state[team]

    def _regress(vals):
        if not vals:
            return _LEAGUE_AVG_XG
        avg = sum(vals) / len(vals)
        n = len(vals)
        return (avg * n + _LEAGUE_AVG_XG * _PRIOR) / (n + _PRIOR)

    predictions = []
    outcomes = {"home_win": 0, "draw": 0, "away_win": 0}
    correct = 0

    for i, game in enumerate(eligible):
        home = game["home_team"]
        away = game["away_team"]
        hs = _get_st(home)
        as_ = _get_st(away)

        # Predict BEFORE recording result
        home_xg = _regress(hs["gf"])
        away_xg = _regress(as_["gf"])

        try:
            from power_ratings import get_elo_diff
            elo_d = get_elo_diff(home, away, "soccer")
        except Exception:
            elo_d = 0

        features = {
            "home_xg_regressed": home_xg,
            "away_xg_regressed": away_xg,
            "elo_diff": elo_d,
            "home_advantage_league": 0.45,
        }

        try:
            from soccer_ev_model import SoccerEVModel
            model = SoccerEVModel()
            probs = model.predict_probabilities(features)
        except Exception:
            probs = {"home_win": 0.40, "draw": 0.27, "away_win": 0.33}

        # Predicted outcome = highest probability
        predicted = max(probs, key=probs.get)

        # Actual outcome
        h_score = game["home_score"]
        a_score = game["away_score"]
        if h_score > a_score:
            actual = "home_win"
        elif h_score == a_score:
            actual = "draw"
        else:
            actual = "away_win"

        outcomes[actual] = outcomes.get(actual, 0) + 1
        if predicted == actual:
            correct += 1

        predictions.append({
            "event_id": game["event_id"],
            "predicted": predicted,
            "actual": actual,
            "probs": probs,
            "correct": predicted == actual,
        })

        # Update state
        hs["gf"].append(h_score)
        hs["ga"].append(a_score)
        as_["gf"].append(a_score)
        as_["ga"].append(h_score)

        if i % 50 == 0:
            with _rules_lock:
                _rules_progress[sport]["processed"] = i + 1
                _rules_progress[sport]["current_date"] = game.get("game_date", "")[:10]

    accuracy = round(correct / total * 100, 1) if total > 0 else 0

    metrics = {
        "total_games": total,
        "accuracy": accuracy,
        "correct": correct,
        "outcomes": outcomes,
        "by_outcome": {},
    }

    # Per-outcome accuracy
    for outcome_key in ("home_win", "draw", "away_win"):
        outcome_preds = [p for p in predictions if p["actual"] == outcome_key]
        outcome_correct = sum(1 for p in outcome_preds if p["correct"])
        n = len(outcome_preds)
        metrics["by_outcome"][outcome_key] = {
            "count": n,
            "accuracy": round(outcome_correct / n * 100, 1) if n > 0 else 0,
        }

    with _rules_lock:
        _rules_progress[sport] = {
            "status": "complete",
            "total_games": total,
            "processed": total,
            "metrics": metrics,
        }

    # Save metrics to DB
    try:
        tm_db.save_backtest_metrics(sport, {"model_params": metrics})
    except Exception:
        pass
