import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

# ─── Thread Pool Config ─────────────────────────────────────────────────────
# Configurable via env vars for deployment tuning.
# Defaults are fast for local dev. For Render free tier, set lower values.
_GAME_WORKERS = int(os.environ.get("SCAN_GAME_WORKERS", 4))
_API_WORKERS = int(os.environ.get("SCAN_API_WORKERS", 4))

# ─── Props Cache ────────────────────────────────────────────────────────────
# Cache processed props results to avoid redundant API calls and PRISM analysis
# when multiple users request the same game within a short time window.
_PROPS_CACHE_TTL = 300  # 5 minutes
_props_cache = {}
_props_cache_lock = threading.Lock()
from api_client import (
    get_todays_games, get_all_injuries, get_game_spread,
    get_player_season_averages, get_game_overunder,
    get_team_recent_results, is_game_stale,
    check_back_to_back, get_previous_matchup,
    get_odds_comparison,
    get_team_roster_leaders, get_team_defensive_stats, get_team_stats,
    get_player_game_log, get_player_props_odds,
)
from api_odds import get_player_props_odds_full
import tracker
from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot, score_line_movement
from trell_rule import is_star_player, is_recent_injury, evaluate_trell_rule
from prism import calculate_prism_projection, get_league_defensive_average, _apply_slot_integration, _calculate_confidence
from rank_analysis import (
    _get_rank_tier, _detect_rank_scam, _detect_spread_discrepancy,
)
from constants import get_max_score, get_recommendation, ML_THRESHOLDS, NBA_UNVALIDATED_CAPS, UNVALIDATED_SPORTS
from calibration import get_calibrated_cover_pct
from analysis_factors import (
    NFL_INDOOR_STADIUMS, H2H_REVENGE_THRESHOLDS,
    _analyze_nfl_trend_discrepancy, _analyze_nfl_overunder, _analyze_nfl_weather,
    _analyze_overunder,
    _get_feedback_adjustment, _analyze_ats_record, _analyze_public_betting,
    _analyze_back_to_back, _analyze_head_to_head, _analyze_home_away_split,
    _detect_vegas_trap,
    _calculate_score, _determine_lean, _fmt_spread,
)


def compute_kelly_sizing(cover_pct, recommendation, sport="nba", ev_model=None):
    """Half-Kelly bet sizing. Returns {kelly_fraction, kelly_pct, suggested_units} or None."""
    if recommendation == "MONITOR" or cover_pct is None:
        return None
    # No Kelly without EV model for unvalidated sports (coin flip OOS)
    if sport in UNVALIDATED_SPORTS and not (ev_model and ev_model.get("active")):
        return None
    # Use EV probability if available, else calibrated cover_pct
    p = (ev_model["probability"] / 100.0) if (ev_model and ev_model.get("active") and ev_model.get("probability")) else (cover_pct / 100.0)
    b = 100.0 / 110.0  # -110 payout
    q = 1.0 - p
    full_kelly = (p * b - q) / b
    if full_kelly <= 0:
        return None
    half_kelly = full_kelly / 2.0
    # Map to units: 1.5% bankroll = 1 unit, round to 0.5u, cap 0.5-3u
    raw = half_kelly * 100 / 1.5
    units = round(raw * 2) / 2
    units = max(0.5, min(3.0, units))
    # Cap by recommendation tier
    if recommendation == "LEAN":
        units = min(units, 1.0)
    elif recommendation == "CONFIDENT":
        units = min(units, 2.0)
    return {
        "kelly_fraction": round(half_kelly, 4),
        "kelly_pct": round(half_kelly * 100, 2),
        "suggested_units": units,
    }


def classify_game_slot(game_date_str, day_of_week, sport, is_first_game=False,
                       total_games_on_slate=1, game_index=0,
                       is_last_sunday_game=False):
    """
    Classify a game's slot type from its date/time.
    Single source of truth — used by scan, predict, and backtest.

    Returns:
        (slot_type, hour, minute, game_time_est) tuple.
        hour/minute may be None if parsing fails.
    """
    hour, minute = None, None
    game_time_est = ""

    if game_date_str:
        try:
            game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))

            # Classification timezone
            if sport in ("cfb", "cbb"):
                classify_dt = game_dt - timedelta(hours=5)  # EST (same as display)
            elif sport == "nhl":
                classify_dt = game_dt - timedelta(hours=6)  # CST
            else:
                classify_dt = game_dt - timedelta(hours=8)  # PST (NBA & NFL)
            hour, minute = classify_dt.hour, classify_dt.minute

            # Use game's own date for day_of_week (important for tomorrow's games)
            day_of_week = classify_dt.strftime("%A")

            # Display timezone: always EST
            est_dt = game_dt - timedelta(hours=5)
            try:
                game_time_est = est_dt.strftime("%-I:%M %p")
            except ValueError:
                game_time_est = est_dt.strftime("%I:%M %p").lstrip("0")
        except (ValueError, TypeError):
            pass

    # Classify slot
    if sport == "nfl":
        if hour is not None:
            slot_type = classify_slot(
                day_of_week, hour, minute,
                sport="nfl",
                is_last_sunday_game=is_last_sunday_game,
            )
        else:
            slot_type = "unknown"
    elif sport in ("cfb", "cbb"):
        if hour is not None:
            slot_type = classify_slot(day_of_week, hour, minute, sport=sport)
        else:
            slot_type = "unknown"
    elif sport == "nhl":
        if hour is not None:
            slot_type = classify_slot(
                day_of_week, hour, minute,
                sport="nhl",
                total_games_on_slate=total_games_on_slate,
                game_index=game_index,
            )
        else:
            slot_type = "unknown"
    else:
        # NBA: first-game override
        if is_first_game:
            slot_type = first_game_slot_override(day_of_week)
        elif hour is not None:
            slot_type = classify_slot(day_of_week, hour, minute)
        else:
            slot_type = "unknown"

    return slot_type, hour, minute, game_time_est, day_of_week


def scan_all_games(sport="nba", date_str=None):
    """
    Fetch all today's games, analyze each, return ranked list.

    Args:
        sport: "nba", "nhl", "cfb", or "nfl"
        date_str: Optional YYYYMMDD to fetch a specific date.

    Returns:
        List of analysis dicts sorted by confirmation_score descending.
    """
    if date_str:
        # Specific date requested — use only that date
        games = get_todays_games(sport, date_str=date_str)
        for g in games:
            g["date_label"] = ""
    else:
        # Fetch today's + tomorrow's scoreboards in parallel
        now_utc = datetime.now(timezone.utc)
        tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y%m%d")

        with ThreadPoolExecutor(max_workers=2) as pool:
            today_future = pool.submit(get_todays_games, sport)
            tomorrow_future = pool.submit(get_todays_games, sport, tomorrow_str)
            today_games = today_future.result()
            tomorrow_games = tomorrow_future.result()

        for g in today_games:
            g["date_label"] = "Today"
        for g in tomorrow_games:
            g["date_label"] = "Tomorrow"

        games = today_games + tomorrow_games

    if not games:
        return []

    all_injuries = get_all_injuries(sport)

    # Save injury snapshot for historical tracking (prospective collection)
    try:
        from test_model.db import upsert_historical_injury
        from datetime import date as _date_type
        today_str = datetime.now().strftime("%Y-%m-%d")
        for team_name, injuries in all_injuries.items():
            for inj in injuries:
                if inj.get("status", "").lower() == "out":
                    upsert_historical_injury(
                        sport=sport,
                        game_date=today_str,
                        team=team_name,
                        player_name=inj.get("player_name", ""),
                        status=inj.get("status", ""),
                    )
    except Exception:
        pass

    # Fetch odds data once for sharp money factor (graceful if no API key)
    try:
        odds_data = get_odds_comparison(sport)
    except Exception:
        odds_data = []

    # Sort by game_date to determine first game / game index
    sorted_games = sorted(games, key=lambda g: g.get("game_date", ""))

    # Filter out stale and final games
    sorted_games = [
        g for g in sorted_games
        if not is_game_stale(g.get("game_date", ""))
        and g.get("game_status") != "STATUS_FINAL"
    ]

    if not sorted_games:
        return []

    total_games = len(sorted_games)

    now = datetime.now()
    day_of_week = now.strftime("%A")

    # NFL: detect last non-SNF Sunday game
    last_sunday_non_snf_idx = None
    if sport == "nfl" and now.strftime("%A").lower() == "sunday":
        for i in range(len(sorted_games) - 1, -1, -1):
            gd = sorted_games[i].get("game_date", "")
            if gd:
                try:
                    gdt = datetime.fromisoformat(gd.replace("Z", "+00:00"))
                    pst_dt = gdt - timedelta(hours=8)
                    pst_mins = pst_dt.hour * 60 + pst_dt.minute
                    snf_mins = 17 * 60 + 20
                    if abs(pst_mins - snf_mins) > 30:
                        last_sunday_non_snf_idx = i
                        break
                except (ValueError, TypeError):
                    continue

    def _analyze_game_wrapper(args):
        i, game = args
        is_first_game = (i == 0)
        is_last_sunday = (i == last_sunday_non_snf_idx) if last_sunday_non_snf_idx is not None else False
        is_tomorrow = game.get("date_label") == "Tomorrow"
        return _analyze_single_game(
            game, day_of_week, all_injuries, is_first_game,
            sport=sport, total_games_on_slate=total_games, game_index=i,
            is_last_sunday_game=is_last_sunday,
            odds_data=odds_data,
            lightweight=is_tomorrow,
        )

    with ThreadPoolExecutor(max_workers=_GAME_WORKERS) as pool:
        results = list(pool.map(_analyze_game_wrapper, enumerate(sorted_games)))

    # Sort by confirmation_score descending
    results.sort(key=lambda r: r.get("confirmation_score", 0), reverse=True)
    return results


def _process_line_movement(opening, current, slot_type):
    """
    Process spread line movement data.
    Returns (line_confirms, line_magnitude, line_toward_dog, line_toward_fav).
    """
    if opening is None or current is None:
        return False, 0.0, False, False

    movement, magnitude = detect_movement(opening, current)
    confirmed = confirms_slot(movement, slot_type)

    # NBA V5: raw line direction toward dog/fav
    raw_movement = current - opening
    toward_dog = False
    toward_fav = False
    if current < 0:  # home favored
        toward_dog = raw_movement > 0.5
        toward_fav = raw_movement < -0.5
    elif current > 0:  # away favored
        toward_dog = raw_movement < -0.5
        toward_fav = raw_movement > 0.5

    return confirmed, magnitude, toward_dog, toward_fav


def _build_action_string(lean_team, current_spread, home_team, moneyline_recommend):
    """Build the action recommendation string with spread numbers."""
    if not lean_team or current_spread is None:
        return None

    if lean_team == home_team:
        lean_spread = current_spread
    else:
        lean_spread = -current_spread
    limit = lean_spread - 1.5
    spread_action = ("Take " + lean_team + " " + _fmt_spread(lean_spread) +
                     " or better — don't take past " + _fmt_spread(limit))
    if moneyline_recommend:
        return (spread_action + " (Best Bet)"
                + " | " + lean_team + " ML (Aggressive)")
    return spread_action


def _build_game_result(game, sport, score, cover_pct, recommendation, lean_team,
                       action, slot_type, game_time_est, current_spread,
                       rank_scam, spread_discrepancy,
                       nfl_weather, nfl_trend, nfl_overunder,
                       b2b_result, ats_result, public_betting_result,
                       h2h_result, vegas_trap_result,
                       cover_pct_calibrated=None, opening_spread=None):
    """Assemble the final result dict for a game analysis."""
    home_team = game["home_team"]
    away_team = game["away_team"]

    result = {
        "home_team": home_team,
        "away_team": away_team,
        "event_id": game["event_id"],
        "game_date": game.get("game_date", ""),
        "game_time_est": game_time_est,
        "date_label": game.get("date_label", ""),
        "confirmation_score": score,
        "cover_pct": cover_pct,
        "cover_pct_calibrated": cover_pct_calibrated,
        "lean_team": lean_team,
        "action": action,
        "recommendation": recommendation,
        "current_spread": current_spread,
        "opening_spread": opening_spread,
    }

    # Venue for NHL, CFB, CBB, and NFL
    if sport in ("nhl", "cfb", "cbb", "nfl"):
        result["venue_name"] = game.get("venue_name", "")
        result["venue_city"] = game.get("venue_city", "")
        result["venue_state"] = game.get("venue_state", "")

    # Rank data and slot info for CFB and CBB
    if sport in ("cfb", "cbb"):
        result["home_rank"] = game.get("home_rank")
        result["away_rank"] = game.get("away_rank")
        result["slot_type"] = slot_type
        if rank_scam["is_rank_scam"]:
            result["rank_scam"] = rank_scam
        if spread_discrepancy["is_discrepancy"]:
            result["spread_discrepancy"] = spread_discrepancy

    # O/U data (all sports)
    if nfl_overunder.get("applies"):
        result["overunder"] = nfl_overunder

    # NFL-specific data
    if sport == "nfl":
        result["slot_type"] = slot_type
        if nfl_weather.get("is_dome"):
            result["weather_dome"] = True
        elif nfl_weather.get("weather") or nfl_weather.get("alerts"):
            result["weather"] = nfl_weather.get("weather", {})
            result["weather_alerts"] = nfl_weather.get("alerts", [])
        if nfl_trend.get("applies"):
            result["trend_discrepancy"] = nfl_trend

    # Factor badges
    if b2b_result["b2b_bonus"] or b2b_result["b2b_penalty"]:
        result["b2b"] = b2b_result
    if ats_result["ats_bonus"] or ats_result["ats_penalty"]:
        result["ats_record"] = ats_result
    if public_betting_result["public_betting_bonus"] > 0:
        result["public_betting"] = public_betting_result
    if h2h_result["h2h_revenge_bonus"] or h2h_result["h2h_dominance_bonus"]:
        result["head_to_head"] = h2h_result
    if vegas_trap_result["is_vegas_trap"]:
        result["vegas_trap"] = vegas_trap_result

    return result


def _detect_pace_mismatch(home_stats, away_stats, home_team, away_team, sport="nba"):
    """
    Detect extreme pace gap between two teams.
    Pace proxy = (avgPoints + avgPointsAgainst) / 2, or avgPoints only as fallback.
    """
    result = {"is_mismatch": False}
    if not home_stats and not away_stats:
        return result

    def _pace(stats):
        if not stats:
            return None
        # Prefer real possessions estimate: FGA - OREB + TOV + 0.44 * FTA
        fga = stats.get("avgFieldGoalsAttempted")
        fta = stats.get("avgFreeThrowsAttempted")
        oreb = stats.get("avgOffensiveRebounds")
        tov = stats.get("avgTurnovers")
        if fga and fta and oreb is not None and tov is not None:
            return round(fga - oreb + tov + 0.44 * fta, 1)
        # Fallback: points-based proxy
        pts_for = stats.get("avgPoints") or stats.get("avgPointsFor")
        pts_against = stats.get("avgPointsAgainst")
        if pts_for and pts_against:
            return round((pts_for + pts_against) / 2, 1)
        if pts_for:
            return round(pts_for, 1)
        return None

    home_pace = _pace(home_stats)
    away_pace = _pace(away_stats)
    if home_pace is None or away_pace is None:
        return result

    gap = round(abs(home_pace - away_pace), 1)
    threshold = 3.0 if sport == "nhl" else 5.0

    if gap >= threshold:
        if home_pace > away_pace:
            fast_team, slow_team = home_team, away_team
            fast_pace, slow_pace = home_pace, away_pace
        else:
            fast_team, slow_team = away_team, home_team
            fast_pace, slow_pace = away_pace, home_pace
        return {
            "is_mismatch": True,
            "fast_team": fast_team,
            "slow_team": slow_team,
            "fast_pace": fast_pace,
            "slow_pace": slow_pace,
            "gap": gap,
            "combined_pace": round((home_pace + away_pace) / 2, 1),
        }

    return result


def _analyze_single_game(game, day_of_week, all_injuries, is_first_game,
                          sport="nba", total_games_on_slate=1, game_index=0,
                          is_last_sunday_game=False, odds_data=None,
                          lightweight=False):
    """
    Returns analysis dict for one game.
    lightweight=True skips expensive API calls (PRISM, B2B, H2H, NFL weather/trends)
    — used for tomorrow's games where deep analysis isn't needed yet.
    """
    event_id = game["event_id"]
    home_team = game["home_team"]
    away_team = game["away_team"]
    game_date_str = game.get("game_date", "")

    # Parse game time + classify slot (shared helper)
    slot_type, hour, minute, game_time_est, day_of_week = classify_game_slot(
        game_date_str, day_of_week, sport,
        is_first_game=is_first_game,
        total_games_on_slate=total_games_on_slate,
        game_index=game_index,
        is_last_sunday_game=is_last_sunday_game,
    )

    # NFL: early return for SKIP slot
    if sport == "nfl" and slot_type == "skip":
        return {
            "home_team": home_team,
            "away_team": away_team,
            "event_id": event_id,
            "game_date": game_date_str,
            "game_time_est": game_time_est,
            "date_label": game.get("date_label", ""),
            "confirmation_score": 0,
            "cover_pct": 0,
            "lean_team": None,
            "action": None,
            "recommendation": "SKIP",
            "slot_type": "skip",
            "skip": True,
            "venue_name": game.get("venue_name", ""),
            "venue_city": game.get("venue_city", ""),
            "venue_state": game.get("venue_state", ""),
        }

    home_team_id = game.get("home_team_id")
    away_team_id = game.get("away_team_id")
    home_rank = game.get("home_rank")
    away_rank = game.get("away_rank")

    # ── Phase 1: Fire ALL independent API calls in parallel ──────────
    # Collect injured player IDs that need stat lookups
    injured_entries = []  # (team_name, injury_dict)
    for team_name in [home_team, away_team]:
        for injury in all_injuries.get(team_name, []):
            if injury.get("status", "").lower() == "out":
                injured_entries.append((team_name, injury))

    with ThreadPoolExecutor(max_workers=_API_WORKERS) as api_pool:
        # Spread
        spread_future = api_pool.submit(get_game_spread, event_id, sport)

        # Injured player stats (parallel)
        injury_stat_futures = []
        for team_name, injury in injured_entries:
            pid = injury.get("player_id")
            if pid:
                f = api_pool.submit(get_player_season_averages, pid, sport)
            else:
                f = None
            injury_stat_futures.append((team_name, injury, f))

        # Phase 1b: non-lightweight factors that don't depend on spread
        b2b_home_future = None
        b2b_away_future = None
        h2h_future = None
        nfl_trend_future = None
        nfl_weather_future = None
        ou_future = None
        home_stats_future = None
        away_stats_future = None

        if not lightweight:
            if sport in ("nba", "nhl") and home_team_id and away_team_id:
                b2b_home_future = api_pool.submit(check_back_to_back, home_team_id, game_date_str, sport)
                b2b_away_future = api_pool.submit(check_back_to_back, away_team_id, game_date_str, sport)

            if home_team_id:
                h2h_future = api_pool.submit(get_previous_matchup, home_team_id, away_team, sport)

            if sport == "nfl":
                if slot_type == "vegas" and home_team_id and away_team_id:
                    nfl_trend_future = api_pool.submit(_analyze_nfl_trend_discrepancy, home_team_id, away_team_id)
                nfl_weather_future = api_pool.submit(_analyze_nfl_weather, game, event_id)

            # O/U analysis — validated sports always, unvalidated only on vegas slots
            if home_team_id and away_team_id:
                _run_ou = sport not in UNVALIDATED_SPORTS or slot_type in ("vegas", "trap")
                if _run_ou:
                    ou_future = api_pool.submit(_analyze_overunder, event_id, home_team_id, away_team_id, sport)

            # Team stats for pace mismatch detection
            if home_team_id and away_team_id:
                home_stats_future = api_pool.submit(get_team_stats, home_team_id, sport)
                away_stats_future = api_pool.submit(get_team_stats, away_team_id, sport)

        # ── Collect spread result ──
        opening, current = spread_future.result()

    # ── Process spread / line movement ──
    line_confirms, line_magnitude, line_toward_dog, line_toward_fav = \
        _process_line_movement(opening, current, slot_type)

    # ── Build injured_stars from parallel results ──
    injured_stars = []
    for team_name, injury, stat_future in injury_stat_futures:
        player_stats = stat_future.result() if stat_future else None
        star = False
        star_reason = ""
        if player_stats:
            star, star_reason = is_star_player(player_stats, sport)

        injured_stars.append({
            "player_name": injury["player_name"],
            "is_star": star,
            "star_reason": star_reason,
            "is_recent": is_recent_injury(injury.get("injury_date", "")),
            "status": injury["status"],
            "team": team_name,
            "ppg": player_stats.get("ppg", 0) if player_stats else 0,
        })

    trell_result = evaluate_trell_rule(injured_stars, slot_type)

    # CFB/CBB Rank Scam + Spread Discrepancy (no API calls)
    rank_scam = {"is_rank_scam": False}
    spread_discrepancy = {"is_discrepancy": False}
    if sport in ("cfb", "cbb"):
        rank_scam = _detect_rank_scam(home_rank, away_rank, current, slot_type)
        spread_discrepancy = _detect_spread_discrepancy(home_rank, away_rank, current, slot_type, sport=sport)

    # Moneyline rule
    moneyline_recommend = False
    current_spread = current
    ml_threshold = ML_THRESHOLDS.get(sport)
    if opening is not None and current is not None and ml_threshold:
        if abs(current) >= ml_threshold:
            moneyline_recommend = True

    # Determine lean team
    lean_team = _determine_lean(slot_type, home_team, away_team, current_spread, sport=sport)

    # Trell Rule lean override
    if trell_result.get("applies"):
        trell_team = trell_result.get("star_team")
        if trell_team:
            lean_team = trell_team

    # ── Vegas Trap detection (NBA only) ──
    vegas_trap_result = {"is_vegas_trap": False, "bonus": 0, "detail": "", "fav_record": ""}
    if not lightweight and sport == "nba" and home_team_id and away_team_id:
        vegas_trap_result = _detect_vegas_trap(
            slot_type, current_spread, home_team_id, away_team_id,
            home_team, away_team,
        )

    # ── Collect Phase 1b parallel results + compute factors ──────────
    b2b_result = {"b2b_bonus": False, "b2b_penalty": False, "detail": ""}
    h2h_result = {"h2h_revenge_bonus": False, "h2h_dominance_bonus": False, "detail": ""}
    nfl_trend = {"applies": False}
    nfl_overunder = {"applies": False}
    nfl_weather = {"is_dome": False, "alerts": []}
    ats_result = {"ats_bonus": False, "ats_penalty": False, "detail": ""}
    public_betting_result = {"public_betting_bonus": 0, "detail": ""}
    feedback_adj = 0

    # Home/Away Splits — no API call
    home_away_applies = _analyze_home_away_split(
        lean_team, home_team, slot_type, current_spread,
    )

    if not lightweight:
        # B2B — collect parallel results, then interpret with lean_team
        if b2b_home_future and b2b_away_future:
            home_b2b = b2b_home_future.result()
            away_b2b = b2b_away_future.result()
            lean_is_home = (lean_team == home_team)
            lean_b2b = home_b2b if lean_is_home else away_b2b
            opp_b2b = away_b2b if lean_is_home else home_b2b
            opp_name = away_team if lean_is_home else home_team
            if opp_b2b and not lean_b2b:
                b2b_result = {"b2b_bonus": True, "b2b_penalty": False,
                              "detail": f"{opp_name} on B2B — rest advantage for {lean_team}"}
            elif lean_b2b and not opp_b2b:
                b2b_result = {"b2b_bonus": False, "b2b_penalty": True,
                              "detail": f"{lean_team} on B2B — fatigue risk"}

        # H2H — collect parallel result, then interpret with lean_team
        if h2h_future:
            matchup = h2h_future.result()
            if matchup is not None:
                threshold = H2H_REVENGE_THRESHOLDS.get(sport, 10)
                margin = matchup["margin"]
                lean_is_home = (lean_team == home_team) if lean_team else False
                lean_margin = margin if lean_is_home else -margin
                if lean_team:
                    if lean_margin < 0 and abs(lean_margin) >= threshold:
                        h2h_result = {
                            "h2h_revenge_bonus": True, "h2h_dominance_bonus": False,
                            "detail": f"REVENGE — {lean_team} lost by {abs(lean_margin)} "
                                      f"({matchup['team_score']}-{matchup['opp_score']}) last meeting",
                        }
                    elif lean_margin > 0 and lean_margin >= threshold:
                        h2h_result = {
                            "h2h_revenge_bonus": False, "h2h_dominance_bonus": True,
                            "detail": f"PRIOR WIN — {lean_team} won by {lean_margin} "
                                      f"({matchup['team_score']}-{matchup['opp_score']}) last meeting",
                        }

        # NFL parallel results
        if nfl_trend_future:
            nfl_trend = nfl_trend_future.result()
        if nfl_weather_future:
            nfl_weather = nfl_weather_future.result()

        # O/U result (all sports)
        if ou_future:
            nfl_overunder = ou_future.result()

        # ATS + public betting + feedback — cheap (local DB / pre-fetched data)
        ats_result = _analyze_ats_record(lean_team, sport)
        public_betting_result = _analyze_public_betting(
            odds_data or [], home_team, away_team, lean_team, slot_type,
        )
        feedback_adj = _get_feedback_adjustment(slot_type, sport)

        # PRISM Player Props — now loaded on-demand via /api/props
        # (removed from scan loop to speed up Quick Picks)

    # Pace mismatch detection (uses team stats from parallel fetch)
    pace_mismatch = {"is_mismatch": False}
    if not lightweight:
        home_stats = home_stats_future.result() if home_stats_future else None
        away_stats = away_stats_future.result() if away_stats_future else None
        pace_mismatch = _detect_pace_mismatch(home_stats, away_stats, home_team, away_team, sport)

    # Calculate score and cover percentage
    rank_scam_applies = rank_scam.get("is_rank_scam", False)
    spread_disc_applies = spread_discrepancy.get("is_discrepancy", False)
    trend_disc_applies = nfl_trend.get("applies", False)
    ou_disc_applies = nfl_overunder.get("applies", False)
    weather_applies = bool(nfl_weather.get("alerts"))

    score, score_breakdown = _calculate_score(
        slot_type, line_confirms, trell_result.get("applies", False),
        line_magnitude=line_magnitude,
        rank_scam_applies=rank_scam_applies, spread_disc_applies=spread_disc_applies,
        trend_disc_applies=trend_disc_applies, ou_disc_applies=ou_disc_applies,
        weather_applies=weather_applies,
        spread_value=current, sport=sport,
        b2b_bonus=b2b_result["b2b_bonus"],
        b2b_penalty=b2b_result["b2b_penalty"],
        ats_bonus=ats_result["ats_bonus"],
        ats_penalty=ats_result["ats_penalty"],
        home_away_applies=home_away_applies,
        public_betting_bonus=public_betting_result["public_betting_bonus"],
        feedback_adjustment=feedback_adj,
        h2h_revenge_bonus=h2h_result["h2h_revenge_bonus"],
        h2h_dominance_bonus=h2h_result["h2h_dominance_bonus"],
        vegas_trap_bonus=vegas_trap_result["bonus"],
        line_toward_dog=line_toward_dog,
        line_toward_fav=line_toward_fav,
        day_of_week=day_of_week,
    )
    max_score = get_max_score(sport)
    cover_pct = round(50 + (score / max_score) * 45, 1)
    cover_pct_cal = get_calibrated_cover_pct(score, sport)

    recommendation = get_recommendation(score, slot_type, sport)

    # ── NBA: track unvalidated factor usage ────────────────────────────
    crossed_unvalidated = False
    if sport == "nba":
        _unval_keys = ("trell", "vegas_trap", "public_betting")
        crossed_unvalidated = any(score_breakdown.get(k, 0) != 0 for k in _unval_keys)

    # ── EV Model Override (NBA + NHL) ─────────────────────────────────
    ev_model_data = None
    if sport in ("nba", "nhl", "cbb") and not lightweight:
        ev_result = _try_ev_prediction(
            sport, current, opening, game.get("game_date", ""),
            home_team, away_team,
        )
        if ev_result:
            score = ev_result["confirmation_score"]
            cover_pct = ev_result["model_probability"]
            cover_pct_cal = ev_result["model_probability"]
            recommendation = ev_result["recommendation"]
            ev_model_data = {
                "probability": ev_result["model_probability"],
                "edge": ev_result["edge"],
                "ev_per_unit": ev_result["ev_per_unit"],
                "auc": ev_result["auc"],
                "active": True,
            }

    action = _build_action_string(lean_team, current_spread, home_team, moneyline_recommend)

    result = _build_game_result(
        game, sport, score, cover_pct, recommendation, lean_team,
        action, slot_type, game_time_est, current_spread,
        rank_scam, spread_discrepancy,
        nfl_weather, nfl_trend, nfl_overunder,
        b2b_result, ats_result, public_betting_result,
        h2h_result, vegas_trap_result,
        cover_pct_calibrated=cover_pct_cal,
        opening_spread=opening,
    )

    if ev_model_data:
        result["ev_model"] = ev_model_data

    if pace_mismatch.get("is_mismatch"):
        result["pace_mismatch"] = pace_mismatch

    # ── Kelly Criterion bet sizing ────────────────────────────────────
    kelly_data = compute_kelly_sizing(cover_pct_cal or cover_pct, recommendation, sport=sport, ev_model=ev_model_data)
    if kelly_data:
        result["kelly"] = kelly_data

    # ── Dynamic validation gate ──────────────────────────────────────
    # Cap recommendations from models that don't beat breakeven OOS.
    try:
        from model_selection import get_validation_tier
        tier, best_oos, best_model = get_validation_tier(sport)
        if tier == "degraded" and recommendation == "STRONG PLAY":
            recommendation = "LEAN"
            result["recommendation"] = recommendation
            # Recompute Kelly with capped recommendation
            kelly_data = compute_kelly_sizing(cover_pct_cal or cover_pct, "LEAN", sport=sport, ev_model=ev_model_data)
            result["kelly"] = kelly_data if kelly_data else result.pop("kelly", None)
    except Exception:
        tier, best_oos, best_model = "degraded", None, None

    # Per-sport validation badge (dynamic from model comparison, static fallback)
    from constants import SPORT_VALIDATION_STATUS, VALIDATION_TIERS
    tier_cfg = VALIDATION_TIERS.get(tier, {})
    if best_oos is not None:
        result["model_status"] = tier_cfg.get("label", "UNKNOWN")
        result["model_status_text"] = f"{tier_cfg.get('label', '?')} \u2014 {best_oos:.0f}% OOS ({best_model or '?'})"
        result["model_status_class"] = tier_cfg.get("css_class", "")
    else:
        _vs = SPORT_VALIDATION_STATUS.get(sport, {})
        result["model_status"] = _vs.get("badge", "UNKNOWN")
        result["model_status_text"] = _vs.get("text", "")
        result["model_status_class"] = _vs.get("css_class", "")

    result["validation_tier"] = tier
    result["best_model_type"] = best_model
    result["best_oos_accuracy"] = best_oos
    if sport == "nba":
        result["crossed_unvalidated"] = crossed_unvalidated

    return result


def _try_ev_prediction(sport, current_spread, opening_spread, game_date_str,
                       home_team, away_team):
    """
    Attempt EV model prediction for NBA or NHL.
    Returns ev_result dict or None if model not active.
    """
    try:
        if current_spread is None:
            return None

        if sport == "nba":
            from nba_ev_model import is_ev_model_active, extract_live_features, predict_single
        elif sport == "nhl":
            from nhl_ev_model import is_ev_model_active, extract_live_features, predict_single
        elif sport == "cbb":
            from cbb_ev_model import is_ev_model_active, extract_live_features, predict_single
        else:
            return None

        if not is_ev_model_active():
            return None

        features = extract_live_features(
            current_spread, opening_spread, None,
            home_team, away_team, game_date_str,
        )
        if features is None:
            return None

        return predict_single(features)
    except Exception:
        return None


def _detect_combo_streak(recent_games, combo_line, stat_keys):
    """
    Streak detection for combo stats — 4+/5 games over or under the combo line.

    Args:
        recent_games: list of game log dicts
        combo_line: the combined line to compare against
        stat_keys: list of stat keys to sum (e.g. ["pts", "reb", "ast"])

    Returns:
        dict {direction, count} or None
    """
    if not recent_games or len(recent_games) < 5:
        return None

    key_map = {"pts": "pts", "reb": "reb", "ast": "ast", "goa": "g", "sog": "sog"}
    fields = [key_map.get(k, k) for k in stat_keys]

    over_count = 0
    under_count = 0
    for g in recent_games[:5]:
        total = 0
        valid = True
        for f in fields:
            val = g.get(f)
            if val is None or not isinstance(val, (int, float)):
                valid = False
                break
            total += float(val)
        if not valid:
            continue
        if total > combo_line:
            over_count += 1
        elif total < combo_line:
            under_count += 1

    if over_count >= 4:
        return {"direction": "OVER", "count": over_count}
    elif under_count >= 4:
        return {"direction": "UNDER", "count": under_count}

    return None


def _run_prism_analysis(home_team_id, away_team_id, home_team, away_team,
                        event_id, game_date_str, current_spread, slot_type,
                        injured_stars, player_props_lines, sport,
                        home_b2b=None, away_b2b=None, game_total=None):
    """
    Runs PRISM player prop analysis for a single game.
    Gets roster leaders, game logs, defensive stats, and generates projections.

    Pre-fetched data can be passed in to avoid redundant API calls:
        home_b2b / away_b2b: bool results from check_back_to_back()
        game_total: float from get_game_overunder()

    Returns:
        List of prop signal dicts sorted by abs(edge) descending,
        filtered to non-PASS signals only.
    """
    results = []

    # ── Fire roster leaders, defensive stats, and any missing data in parallel ──
    with ThreadPoolExecutor(max_workers=_API_WORKERS) as prism_pool:
        home_leaders_f = prism_pool.submit(get_team_roster_leaders, home_team_id, sport=sport, limit=3)
        away_leaders_f = prism_pool.submit(get_team_roster_leaders, away_team_id, sport=sport, limit=3)
        home_stats_f = prism_pool.submit(get_team_stats, home_team_id, sport=sport)
        away_stats_f = prism_pool.submit(get_team_stats, away_team_id, sport=sport)

        # Only fetch if not pre-supplied
        game_total_f = None
        home_b2b_f = None
        away_b2b_f = None
        if game_total is None:
            game_total_f = prism_pool.submit(get_game_overunder, event_id, sport=sport)
        if home_b2b is None:
            home_b2b_f = prism_pool.submit(check_back_to_back, home_team_id, game_date_str, sport)
        if away_b2b is None:
            away_b2b_f = prism_pool.submit(check_back_to_back, away_team_id, game_date_str, sport)

        home_leaders = home_leaders_f.result()
        away_leaders = away_leaders_f.result()
        home_team_stats = home_stats_f.result()
        away_team_stats = away_stats_f.result()
        if game_total_f is not None:
            game_total = game_total_f.result()
        if home_b2b_f is not None:
            home_b2b = home_b2b_f.result()
        if away_b2b_f is not None:
            away_b2b = away_b2b_f.result()

    # Tag each leader with their team info and rank (0=top scorer, 1=2nd, 2=3rd)
    for i, p in enumerate(home_leaders):
        p["_team"] = home_team
        p["_team_id"] = home_team_id
        p["_is_home"] = True
        p["_opp_team_id"] = away_team_id
        p["_rank"] = i
    for i, p in enumerate(away_leaders):
        p["_team"] = away_team
        p["_team_id"] = away_team_id
        p["_is_home"] = False
        p["_opp_team_id"] = home_team_id
        p["_rank"] = i

    all_players = home_leaders + away_leaders

    # Filter out injured-OUT players
    out_names = {s["player_name"].lower() for s in injured_stars
                 if s.get("status", "").lower() == "out"}
    all_players = [p for p in all_players if p["name"].lower() not in out_names]

    if not all_players:
        return results

    league_avg_def = get_league_defensive_average(sport)

    # Pre-map full team stats by team_id (used for matchup multipliers)
    stats_by_team = {home_team_id: home_team_stats, away_team_id: away_team_stats}

    # ── Fetch all game logs in parallel ──
    with ThreadPoolExecutor(max_workers=_API_WORKERS) as log_pool:
        game_log_futures = {}
        for player in all_players:
            if player.get("ppg", 0) > 0:
                game_log_futures[player["name"]] = log_pool.submit(
                    get_player_game_log, player["name"], count=7, sport=sport,
                    athlete_id=player.get("athlete_id"), team_id=player.get("_team_id")
                )

    # Stat types to analyze: (stat_key, season_avg_key, label, odds_key, min_avg)
    if sport == "nhl":
        stat_configs = [
            ("pts", "ppg", "PTS", "points", 0.5),       # Points (goals+assists), min 0.5 PPG
            ("g", "gpg", "GOALS", "goals", 0.2),         # Goals per game, min 0.2
            ("ast", "apg", "AST", "assists", 0.3),       # Assists per game, min 0.3
            ("sog", "sogpg", "SOG", "shots_on_goal", 1.5),  # Shots on goal, min 1.5
        ]
    else:
        stat_configs = [
            ("pts", "ppg", "PTS", "points", 8.0),
            ("reb", "rpg", "REB", "rebounds", 4.0),
            ("ast", "apg", "AST", "assists", 3.0),
        ]

    for player in all_players:
        player_name = player["name"]

        if player.get("ppg", 0) <= 0:
            continue

        # Get opponent stats (full team stats, already fetched)
        opp_stats = stats_by_team.get(player["_opp_team_id"]) or {}
        if sport == "nhl":
            opp_def_rating = opp_stats.get("avgGoalsAllowed") or opp_stats.get("avgPointsAgainst")
        else:
            opp_def_rating = opp_stats.get("avgPointsAgainst") or opp_stats.get("pts_allowed_per_game")

        # Get game log (already fetched in parallel)
        recent_games = game_log_futures[player_name].result() if player_name in game_log_futures else None

        # B2B status for this player's team
        is_b2b = home_b2b if player["_is_home"] else away_b2b

        # Injured teammates on this player's team
        team_name = player["_team"]
        injured_teammates = [
            {"name": s["player_name"], "ppg": s.get("ppg", 0)}
            for s in injured_stars
            if s.get("team") == team_name
            and s.get("status", "").lower() == "out"
            and s.get("ppg", 0) > 0
        ]

        # Odds lines for this player
        norm_name = player_name.strip().lower()
        player_odds = player_props_lines.get(norm_name, {})

        for stat_key, avg_key, label, odds_key, min_avg in stat_configs:
            season_avg = player.get(avg_key, 0)

            # NHL SOG: estimate from game logs if not in season averages
            if sport == "nhl" and stat_key == "sog" and season_avg == 0 and recent_games:
                sog_vals = [g.get("sog", 0) for g in recent_games if g.get("sog") is not None]
                if sog_vals:
                    season_avg = sum(sog_vals) / len(sog_vals)

            if season_avg < min_avg:
                continue

            posted_line = player_odds.get(odds_key)
            _line_source = "odds_api" if posted_line is not None else "estimated"

            proj = calculate_prism_projection(
                season_avg=season_avg,
                recent_games=recent_games or [],
                stat_type=stat_key,
                opponent_def_rating=opp_def_rating,
                league_avg_def=league_avg_def,
                game_total=game_total,
                is_b2b=is_b2b,
                is_home=player["_is_home"],
                spread=current_spread,
                injured_teammates=injured_teammates if stat_key == "pts" else [],
                posted_line=posted_line,
                slot_type=slot_type,
                sport=sport,
                player_rank=player.get("_rank", 0),
                opponent_stats=opp_stats,
            )

            if proj is None:
                continue

            if proj["signal"] in ("PASS", "SKIP"):
                continue

            results.append({
                "player_name": player_name,
                "team": team_name,
                "stat_type": label,
                "projection": proj["projection"],
                "line": proj["line"],
                "line_source": _line_source,
                "edge": proj["edge"],
                "signal": proj["signal"],
                "confidence": proj["confidence"],
                "streak": proj["streak"],
                "minutes_unstable": proj["minutes_unstable"],
                "slot_type": slot_type,
                "recent_games": recent_games or [],
                "is_b2b": is_b2b or False,
                "has_injury_boost": bool(injured_teammates) and stat_key == "pts",
                "stat_key": stat_key,
            })

    # ── Combo Props ──────────────────────────────────────────────────────────
    # Sum individual PRISM projections — no new model calls needed.
    if sport == "nhl":
        combo_configs = [
            ("GOALS+AST", ["GOALS", "AST"], "goals_assists"),
            ("PTS+SOG",   ["PTS", "SOG"],   "points_shots"),
        ]
    else:
        combo_configs = [
            ("PTS+REB+AST", ["PTS", "REB", "AST"], "points_rebounds_assists"),
            ("PTS+REB",     ["PTS", "REB"],         "points_rebounds"),
            ("PTS+AST",     ["PTS", "AST"],         "points_assists"),
            ("REB+AST",     ["REB", "AST"],         "rebounds_assists"),
        ]

    # Index individual results by (player_name, stat_type) for fast lookup
    indiv_by_player = {}
    for r in results:
        key = (r["player_name"], r["stat_type"])
        indiv_by_player[key] = r

    # Collect unique players that have at least one individual result
    players_with_results = set(r["player_name"] for r in results)

    for player_name in players_with_results:
        for combo_label, required_stats, odds_key in combo_configs:
            # Collect individual results for this combo
            indiv_results = []
            for stat_label in required_stats:
                ir = indiv_by_player.get((player_name, stat_label))
                if ir is None:
                    break
                indiv_results.append(ir)
            else:
                # All required stats present — build combo
                combo_projection = sum(r["projection"] for r in indiv_results)

                # Prefer real combo line from odds, fall back to sum of individual lines
                first_result = indiv_results[0]
                norm_name = player_name.strip().lower()
                player_odds = player_props_lines.get(norm_name, {})
                real_combo_line = player_odds.get(odds_key)
                if real_combo_line is not None:
                    combo_line = float(real_combo_line)
                    combo_line_source = "odds_api"
                else:
                    combo_line = sum(r["line"] for r in indiv_results)
                    combo_line_source = "estimated"

                combo_edge = round(combo_projection - combo_line, 1)

                # Signal via slot integration (same as individual stats)
                combo_signal = _apply_slot_integration(combo_edge, slot_type)
                if combo_signal in ("PASS", "SKIP"):
                    continue

                # Cap estimated lines at LEAN max
                if combo_line_source == "estimated" and combo_signal.startswith("STRONG"):
                    combo_signal = combo_signal.replace("STRONG", "LEAN")

                # Confidence: min of individual confidences minus 5 (combo uncertainty penalty)
                combo_confidence = min(r["confidence"] for r in indiv_results) - 5
                combo_confidence = max(combo_confidence, 20)

                # Streak detection for combo stats
                combo_streak = _detect_combo_streak(
                    first_result.get("recent_games", []),
                    combo_line,
                    [s.lower()[:3] for s in required_stats],
                )

                # stat_key uses "+" separator for EV engine dispatch
                combo_stat_key = "+".join(s.lower()[:3] for s in required_stats)

                results.append({
                    "player_name": player_name,
                    "team": first_result["team"],
                    "stat_type": combo_label,
                    "projection": round(combo_projection, 1),
                    "line": round(combo_line, 1),
                    "line_source": combo_line_source,
                    "edge": combo_edge,
                    "signal": combo_signal,
                    "confidence": combo_confidence,
                    "streak": combo_streak,
                    "minutes_unstable": any(r["minutes_unstable"] for r in indiv_results),
                    "slot_type": slot_type,
                    "recent_games": first_result.get("recent_games", []),
                    "is_b2b": first_result.get("is_b2b", False),
                    "has_injury_boost": any(r.get("has_injury_boost", False) for r in indiv_results),
                    "stat_key": combo_stat_key,
                })

    # Sort by abs(edge) descending
    results.sort(key=lambda x: abs(x["edge"]), reverse=True)

    # Auto-save PRISM predictions for tracking accuracy
    try:
        tracker.save_prism_predictions(results, event_id, sport)
    except Exception:
        pass

    return results


def get_top_props(sport="nba"):
    """
    Fetch today's games and run PRISM analysis for ALL games in parallel.
    Returns a flat list of prop dicts sorted by confidence, each tagged with matchup info.
    """
    if sport not in ("nba", "cbb", "nhl"):
        return []

    games = get_todays_games(sport)
    # Filter out stale/final games
    games = [
        g for g in games
        if not is_game_stale(g.get("game_date", ""))
        and g.get("game_status") != "STATUS_FINAL"
    ]

    if not games:
        return []

    # Fetch league-wide player prop odds ONCE (not per-game)
    try:
        shared_props_odds = get_player_props_odds(sport)
    except Exception:
        shared_props_odds = {}

    def _fetch_props(game):
        eid = str(game["event_id"])
        matchup = game["away_team"] + " @ " + game["home_team"]
        game_date = game.get("game_date", "")
        try:
            props = get_game_props(eid, sport, player_props_lines=shared_props_odds)
        except Exception as e:
            print(f"[get_top_props] Failed for {matchup}: {type(e).__name__}: {str(e)[:100]}", flush=True)
            props = []
        for p in props:
            p["matchup"] = matchup
            p["event_id"] = eid
            p["game_date"] = game_date
        return props

    all_props = []
    max_total_time = 45  # Max 45 seconds total to avoid web server timeout
    start_time = time.time()

    # Use fewer workers for batch to avoid thread explosion (each game spawns sub-pools)
    batch_workers = min(2, len(games))
    with ThreadPoolExecutor(max_workers=batch_workers) as pool:
        futures = {pool.submit(_fetch_props, g): g for g in games}
        for future in as_completed(futures):
            # Check if we've exceeded total time budget
            elapsed = time.time() - start_time
            if elapsed > max_total_time:
                print(f"[get_top_props] Hit {max_total_time}s timeout, skipping remaining games", flush=True)
                break

            try:
                # Reduce per-game timeout to fit within total budget
                remaining = max(5, max_total_time - elapsed)
                result = future.result(timeout=min(30, remaining))
                all_props.extend(result)
            except Exception as e:
                # Log but continue - don't let one game failure break all props
                print(f"[get_top_props] Failed to fetch props: {e}", flush=True)
                pass

    # Sort by confidence descending
    all_props.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    print(f"[get_top_props] Completed in {time.time() - start_time:.1f}s, found {len(all_props)} props", flush=True)
    return all_props


def calculate_prop_ev(projection, line, edge, confidence, signal):
    """
    Calculate expected value for a player prop.

    Args:
        projection: Our projected value
        line: Sportsbook line
        edge: projection - line
        confidence: PRISM confidence score (0-100)
        signal: PRISM signal (STRONG OVER, LEAN UNDER, etc.)

    Returns:
        dict with probability, ev_pct, ev_units, or None if insufficient data
    """
    if projection is None or line is None or line <= 0:
        return None

    # Determine direction - we're betting OVER or UNDER based on edge
    is_over = edge > 0

    # Base probability from confidence (50-95% range, scaled from PRISM confidence)
    # Confidence 50 = 50% win prob, Confidence 95 = 75% win prob
    base_prob = 50 + (confidence - 50) * 0.5

    # Only apply edge boost if edge is in the direction we're betting
    edge_abs = abs(edge)
    edge_pct = edge_abs / line if line > 0 else 0

    # Edge boost: larger edge = more confidence (0-10% boost)
    edge_boost = min(edge_pct * 20, 10) if edge_abs >= 1.0 else 0

    # Signal strength adjustment
    signal_adj = 0
    if "STRONG" in signal:
        signal_adj = 5
    elif "LEAN" in signal:
        signal_adj = 2

    # Final probability (capped 45-90% for safety)
    probability = max(45, min(90, base_prob + edge_boost + signal_adj))

    # Expected value calculation (assuming -110 odds)
    # Breakeven = 52.4% (need to win 11 to win 10)
    # EV% = (win_prob - 52.4) / 52.4 * 100
    breakeven = 52.4
    ev_pct = ((probability - breakeven) / breakeven) * 100

    # EV in units (assuming $100 bet at -110)
    # Win: +$90.91, Lose: -$100
    # EV = (prob * 90.91) - ((1-prob) * 100)
    win_prob_decimal = probability / 100.0
    ev_units = (win_prob_decimal * 90.91) - ((1 - win_prob_decimal) * 100)

    return {
        "probability": round(probability, 1),
        "ev_pct": round(ev_pct, 1),
        "ev_units": round(ev_units, 2),
    }


def get_top_props_with_ev(sport="nba"):
    """
    Fetch all props and add EV calculations.
    Returns props sorted by EV (highest first).
    """
    try:
        props = get_top_props(sport)
    except Exception as e:
        print(f"[get_top_props_with_ev] Failed to fetch props: {e}", flush=True)
        return []

    # Add EV to each prop
    for p in props:
        ev_calc = calculate_prop_ev(
            p.get("projection"),
            p.get("line"),
            p.get("edge", 0),
            p.get("confidence", 0),
            p.get("signal", ""),
        )
        if ev_calc:
            p["ev_probability"] = ev_calc["probability"]
            p["ev_pct"] = ev_calc["ev_pct"]
            p["ev_units"] = ev_calc["ev_units"]
        else:
            p["ev_probability"] = None
            p["ev_pct"] = None
            p["ev_units"] = None

    # Filter to positive EV only and sort by EV
    positive_ev = [p for p in props if p.get("ev_pct") and p["ev_pct"] > 0]
    positive_ev.sort(key=lambda x: x.get("ev_pct", 0), reverse=True)

    return positive_ev


def get_prop_ev_analysis(sport="nba"):
    """
    Full Prop EV pipeline: PRISM projections + actual odds → variance-based EV.

    1. Fetches PRISM props via get_top_props()
    2. Fetches actual market odds via get_player_props_odds_full()
    3. Runs prop_ev_engine.analyze_prop() for each prop
    4. Filters to positive EV, sorts by EV descending

    Returns:
        List of enriched prop dicts with variance, probability, and EV data.
    """
    from prop_ev_engine import analyze_prop

    if sport not in ("nba", "cbb", "nhl"):
        return []

    # Fetch PRISM projections and market odds in parallel
    prism_props = []
    odds_data = {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        prism_f = pool.submit(get_top_props, sport)
        odds_f = pool.submit(get_player_props_odds_full, sport)

        try:
            prism_props = prism_f.result(timeout=55)
        except Exception as e:
            print(f"[get_prop_ev_analysis] PRISM fetch failed: {e}", flush=True)
            prism_props = []

        try:
            odds_data = odds_f.result(timeout=15)
        except Exception:
            odds_data = {}

    if not prism_props:
        return []

    # Map stat_type labels back to odds keys
    label_to_odds_key = {
        "PTS": "points", "REB": "rebounds", "AST": "assists",
        "PTS+REB+AST": "points_rebounds_assists",
        "PTS+REB": "points_rebounds",
        "PTS+AST": "points_assists",
        "REB+AST": "rebounds_assists",
        "GOALS": "goals", "SOG": "shots_on_goal",
        "GOALS+AST": "goals_assists", "PTS+SOG": "points_shots",
    }

    results = []
    for p in prism_props:
        player_name = p.get("player_name", "")
        stat_type = p.get("stat_type", "")
        projection = p.get("projection")
        line = p.get("line")
        recent_games = p.get("recent_games", [])
        stat_key = p.get("stat_key", stat_type.lower()[:3])
        is_b2b = p.get("is_b2b", False)
        minutes_unstable = p.get("minutes_unstable", False)
        has_injury_boost = p.get("has_injury_boost", False)

        # Look up market odds for this player/stat
        norm_name = player_name.strip().lower()
        odds_key = label_to_odds_key.get(stat_type, stat_type.lower())
        player_odds = odds_data.get(norm_name, {}).get(odds_key, {})
        over_odds = player_odds.get("over_odds")
        under_odds = player_odds.get("under_odds")

        ev_analysis = analyze_prop(
            projection=projection,
            line=line,
            recent_games=recent_games,
            stat_key=stat_key,
            is_b2b=is_b2b,
            minutes_unstable=minutes_unstable,
            has_injury_boost=has_injury_boost,
            over_odds=over_odds,
            under_odds=under_odds,
        )

        if ev_analysis is None:
            continue

        # Skip PASS tier and negative EV
        if ev_analysis["tier"] == "PASS":
            continue
        if ev_analysis.get("ev_pct") is not None and ev_analysis["ev_pct"] <= 0:
            continue

        # Merge PRISM fields with EV analysis
        enriched = {
            "player_name": player_name,
            "team": p.get("team", ""),
            "matchup": p.get("matchup", ""),
            "event_id": p.get("event_id", ""),
            "game_date": p.get("game_date", ""),
            "stat_type": stat_type,
            "projection": projection,
            "line": line,
            "line_source": p.get("line_source", "estimated"),
            "edge": p.get("edge", 0),
            "signal": p.get("signal", ""),
            "confidence": p.get("confidence", 0),
            "slot_type": p.get("slot_type", ""),
            # EV engine fields
            "direction": ev_analysis["direction"],
            "std_dev": ev_analysis["std_dev"],
            "adjusted_std": ev_analysis["adjusted_std"],
            "n_games": ev_analysis["n_games"],
            "z_score": ev_analysis["z_score"],
            "model_probability": ev_analysis["model_probability"],
            "implied_probability": ev_analysis["implied_probability"],
            "edge_pct": ev_analysis["edge_pct"],
            "over_odds": ev_analysis["over_odds"],
            "under_odds": ev_analysis["under_odds"],
            "market_odds": ev_analysis["market_odds"],
            "ev_dollars": ev_analysis["ev_dollars"],
            "ev_pct": ev_analysis["ev_pct"],
            "tier": ev_analysis["tier"],
            "has_real_odds": ev_analysis["has_real_odds"],
            "vig_pct": ev_analysis.get("vig_pct"),
        }
        results.append(enriched)

    # Sort by EV$ descending
    results.sort(key=lambda x: x.get("ev_dollars") or 0, reverse=True)
    print(f"[get_prop_ev_analysis] Found {len(results)} positive EV props", flush=True)
    return results


def get_game_props(event_id, sport="nba", player_props_lines=None):
    """
    Standalone PRISM analysis for a single game, invoked on-demand.
    Fetches all needed context from ESPN API and runs _run_prism_analysis().

    Args:
        player_props_lines: Pre-fetched odds dict to avoid redundant league-wide API calls.

    Returns:
        List of prop signal dicts, or empty list on failure.
    """
    start = time.time()
    if sport not in ("nba", "cbb", "nhl"):
        return []

    # Check cache first
    cache_key = f"{sport}:{event_id}"
    now = time.time()
    with _props_cache_lock:
        entry = _props_cache.get(cache_key)
        if entry and (now - entry["ts"]) < _PROPS_CACHE_TTL:
            print(f"[get_game_props] Cache hit for {cache_key} in {time.time()-start:.2f}s", flush=True)
            return entry["data"]

    # Find the game across today + tomorrow
    t1 = time.time()
    now_utc = datetime.now(timezone.utc)
    tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y%m%d")

    game = None
    for date_str in [None, tomorrow_str]:
        games = get_todays_games(sport, date_str=date_str)
        for g in games:
            if str(g["event_id"]) == str(event_id):
                game = g
                break
        if game:
            break

    print(f"[get_game_props] Found game in {time.time()-t1:.2f}s", flush=True)
    if not game:
        print(f"[get_game_props] Game {event_id} not found", flush=True)
        return []

    home_team = game["home_team"]
    away_team = game["away_team"]
    home_team_id = game.get("home_team_id")
    away_team_id = game.get("away_team_id")
    game_date_str = game.get("game_date", "")

    if not home_team_id or not away_team_id:
        return []

    # Classify slot for this game
    hour, minute = None, None
    slot_type = "unknown"
    if game_date_str:
        try:
            game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
            if sport == "cbb":
                classify_dt = game_dt - timedelta(hours=5)  # EST for CBB
            elif sport == "nhl":
                classify_dt = game_dt - timedelta(hours=6)  # CST for NHL
            else:
                classify_dt = game_dt - timedelta(hours=8)  # PST for NBA
            hour, minute = classify_dt.hour, classify_dt.minute
            day_of_week = classify_dt.strftime("%A")
            slot_type = classify_slot(day_of_week, hour, minute, sport=sport)
        except (ValueError, TypeError):
            pass

    # Parallel fetch: spread, B2B, O/U, and optionally player props odds
    # NOTE: Injuries removed from parallel fetch - too slow for league-wide fetch
    t2 = time.time()
    need_odds = player_props_lines is None
    with ThreadPoolExecutor(max_workers=_API_WORKERS) as pool:
        spread_f = pool.submit(get_game_spread, event_id, sport)
        b2b_home_f = pool.submit(check_back_to_back, home_team_id, game_date_str, sport)
        b2b_away_f = pool.submit(check_back_to_back, away_team_id, game_date_str, sport)
        ou_f = pool.submit(get_game_overunder, event_id, sport=sport)
        props_odds_f = pool.submit(get_player_props_odds, sport) if need_odds else None

        opening, current = spread_f.result()
        home_b2b = b2b_home_f.result()
        away_b2b = b2b_away_f.result()
        game_total = ou_f.result()
        if props_odds_f is not None:
            try:
                player_props_lines = props_odds_f.result()
            except Exception:
                player_props_lines = {}
    print(f"[get_game_props] Context fetch completed in {time.time()-t2:.2f}s", flush=True)

    # Build injured_stars list (skip injuries for props - not critical for PRISM)
    # Injuries can take 5-10 seconds for league-wide fetch, so we skip for on-demand props
    injured_stars = []

    # Run PRISM analysis
    t3 = time.time()
    results = _run_prism_analysis(
        home_team_id, away_team_id, home_team, away_team,
        event_id, game_date_str, current, slot_type,
        injured_stars, player_props_lines or {},
        sport,
        home_b2b=home_b2b, away_b2b=away_b2b, game_total=game_total,
    )
    print(f"[get_game_props] PRISM analysis completed in {time.time()-t3:.2f}s", flush=True)

    # Cache the results
    with _props_cache_lock:
        _props_cache[cache_key] = {"data": results, "ts": time.time()}
        # Limit cache size to prevent memory bloat (evict oldest if > 50 games)
        if len(_props_cache) > 50:
            oldest = sorted(_props_cache, key=lambda k: _props_cache[k]["ts"])
            for old_key in oldest[:len(_props_cache) - 50]:
                del _props_cache[old_key]

    print(f"[get_game_props] Total time: {time.time()-start:.2f}s for {len(results)} props", flush=True)

    # Force garbage collection to free memory from API responses
    import gc
    gc.collect()

    return results
