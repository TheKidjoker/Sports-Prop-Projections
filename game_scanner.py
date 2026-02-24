import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

# ─── Thread Pool Config ─────────────────────────────────────────────────────
# Configurable via env vars for deployment tuning.
# Defaults are fast for local dev. For Render free tier, set lower values.
_GAME_WORKERS = int(os.environ.get("SCAN_GAME_WORKERS", 10))
_API_WORKERS = int(os.environ.get("SCAN_API_WORKERS", 8))
from api_client import (
    get_todays_games, get_all_injuries, get_game_spread,
    get_player_season_averages, get_game_overunder,
    get_team_recent_results, is_game_stale,
    check_back_to_back, get_previous_matchup,
    get_odds_comparison,
    get_team_roster_leaders, get_team_defensive_stats,
    get_player_game_log, get_player_props_odds,
)
import tracker
from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot, score_line_movement
from trell_rule import is_star_player, is_recent_injury, evaluate_trell_rule
from prism import calculate_prism_projection, get_league_defensive_average
from rank_analysis import (
    _get_rank_tier, _detect_rank_scam, _detect_spread_discrepancy,
)
from analysis_factors import (
    NFL_INDOOR_STADIUMS, H2H_REVENGE_THRESHOLDS,
    _analyze_nfl_trend_discrepancy, _analyze_nfl_overunder, _analyze_nfl_weather,
    _get_feedback_adjustment, _analyze_ats_record, _analyze_public_betting,
    _analyze_back_to_back, _analyze_head_to_head, _analyze_home_away_split,
    _detect_vegas_trap,
    _calculate_score, _determine_lean, _fmt_spread,
)


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

    # Parse game time
    # NBA: classify using PST (UTC-8), display using EST (UTC-5)
    # NHL: classify using CST (UTC-6), display using EST (UTC-5)
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
        nfl_ou_future = None
        nfl_weather_future = None

        if not lightweight:
            if sport in ("nba", "nhl") and home_team_id and away_team_id:
                b2b_home_future = api_pool.submit(check_back_to_back, home_team_id, game_date_str, sport)
                b2b_away_future = api_pool.submit(check_back_to_back, away_team_id, game_date_str, sport)

            if home_team_id:
                h2h_future = api_pool.submit(get_previous_matchup, home_team_id, away_team, sport)

            if sport == "nfl":
                if slot_type == "vegas" and home_team_id and away_team_id:
                    nfl_trend_future = api_pool.submit(_analyze_nfl_trend_discrepancy, home_team_id, away_team_id)
                    nfl_ou_future = api_pool.submit(_analyze_nfl_overunder, event_id, home_team_id, away_team_id)
                nfl_weather_future = api_pool.submit(_analyze_nfl_weather, game, event_id)

        # ── Collect spread result ──
        opening, current = spread_future.result()

    # ── Process spread / line movement (no API calls) ──
    line_movement_data = {"available": False}
    line_confirms = False
    line_magnitude = 0.0

    if opening is not None and current is not None:
        movement, line_magnitude = detect_movement(opening, current)
        confirmed = confirms_slot(movement, slot_type)
        line_confirms = confirmed
        line_movement_data = {
            "available": True,
            "opening_spread": opening,
            "current_spread": current,
            "movement": movement,
            "magnitude": line_magnitude,
            "confirms_slot": confirmed,
        }

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
    ml_threshold = {"nba": 6, "nfl": 3, "cfb": 7, "cbb": 7}.get(sport)
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
        if nfl_ou_future:
            nfl_overunder = nfl_ou_future.result()
        if nfl_weather_future:
            nfl_weather = nfl_weather_future.result()

        # ATS + public betting + feedback — cheap (local DB / pre-fetched data)
        ats_result = _analyze_ats_record(lean_team, sport)
        public_betting_result = _analyze_public_betting(
            odds_data or [], home_team, away_team, lean_team, slot_type,
        )
        feedback_adj = _get_feedback_adjustment(slot_type, sport)

        # PRISM Player Props — now loaded on-demand via /api/props
        # (removed from scan loop to speed up Quick Picks)

    # Calculate score and cover percentage
    rank_scam_applies = rank_scam.get("is_rank_scam", False)
    spread_disc_applies = spread_discrepancy.get("is_discrepancy", False)
    trend_disc_applies = nfl_trend.get("applies", False)
    ou_disc_applies = nfl_overunder.get("applies", False)
    weather_applies = bool(nfl_weather.get("alerts"))

    score, _ = _calculate_score(
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
    )
    if sport == "nfl":
        max_score = 53
    elif sport == "cfb":
        max_score = 48
    elif sport == "cbb":
        max_score = 33  # Reduced after backtesting adjustments
    elif sport == "nba":
        max_score = 39  # Reduced after backtesting adjustments
    else:
        max_score = 42
    cover_pct = round(50 + (score / max_score) * 45, 1)

    # Recommendation label
    # NBA backtested: sweet spot is score 4-7, public slot drags accuracy.
    # Use lower thresholds + demote public-slot picks.
    # CBB backtested: STRONG PLAY (>=15) at 56.9%, LEAN 10-14 bucket is dead zone.
    if sport == "nba":
        if slot_type == "public":
            # Public slot NBA: never STRONG PLAY, cap at LEAN
            if score >= 7:
                recommendation = "LEAN"
            else:
                recommendation = "MONITOR"
        else:
            if score >= 10:
                recommendation = "STRONG PLAY"
            elif score >= 5:
                recommendation = "LEAN"
            else:
                recommendation = "MONITOR"
    elif sport == "cbb":
        # CBB backtested: raise LEAN bar to avoid 10-14 dead zone
        if score >= 15:
            recommendation = "STRONG PLAY"
        elif score >= 12:
            recommendation = "LEAN"
        else:
            recommendation = "MONITOR"
    else:
        if score >= 15:
            recommendation = "STRONG PLAY"
        elif score >= 10:
            recommendation = "LEAN"
        else:
            recommendation = "MONITOR"

    # Build clear action string with spread numbers
    action = None
    if lean_team and current_spread is not None:
        if moneyline_recommend:
            action = "Take " + lean_team + " Moneyline"
        else:
            # Get the spread from the lean team's perspective
            if lean_team == home_team:
                lean_spread = current_spread
            else:
                lean_spread = -current_spread
            limit = lean_spread - 1.5
            action = ("Take " + lean_team + " " + _fmt_spread(lean_spread) +
                      " or better — don't take past " + _fmt_spread(limit))

    result = {
        "home_team": home_team,
        "away_team": away_team,
        "event_id": event_id,
        "game_date": game_date_str,
        "game_time_est": game_time_est,
        "date_label": game.get("date_label", ""),
        "confirmation_score": score,
        "cover_pct": cover_pct,
        "lean_team": lean_team,
        "action": action,
        "recommendation": recommendation,
        "current_spread": current_spread,
    }

    # Historical accuracy from backtesting (NBA V4 tuned data)
    if sport == "nba" and recommendation != "MONITOR":
        if score >= 10:
            result["historical_accuracy"] = 68.9
            result["historical_sample_size"] = 29
        elif score >= 5:
            result["historical_accuracy"] = 62.7
            result["historical_sample_size"] = 51

    # Include venue for NHL, CFB, CBB, and NFL
    if sport in ("nhl", "cfb", "cbb", "nfl"):
        result["venue_name"] = game.get("venue_name", "")
        result["venue_city"] = game.get("venue_city", "")
        result["venue_state"] = game.get("venue_state", "")

    # Include rank data and slot info for CFB and CBB
    if sport in ("cfb", "cbb"):
        result["home_rank"] = home_rank
        result["away_rank"] = away_rank
        result["slot_type"] = slot_type
        if rank_scam["is_rank_scam"]:
            result["rank_scam"] = rank_scam
        if spread_discrepancy["is_discrepancy"]:
            result["spread_discrepancy"] = spread_discrepancy

    # Include NFL-specific data
    if sport == "nfl":
        result["slot_type"] = slot_type
        if nfl_weather.get("is_dome"):
            result["weather_dome"] = True
        elif nfl_weather.get("weather") or nfl_weather.get("alerts"):
            result["weather"] = nfl_weather.get("weather", {})
            result["weather_alerts"] = nfl_weather.get("alerts", [])
        if nfl_trend.get("applies"):
            result["trend_discrepancy"] = nfl_trend
        if nfl_overunder.get("applies"):
            result["overunder"] = nfl_overunder

    # ── New factor badges ──
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
        home_def_f = prism_pool.submit(get_team_defensive_stats, home_team_id, sport=sport)
        away_def_f = prism_pool.submit(get_team_defensive_stats, away_team_id, sport=sport)

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
        home_def = home_def_f.result()
        away_def = away_def_f.result()
        if game_total_f is not None:
            game_total = game_total_f.result()
        if home_b2b_f is not None:
            home_b2b = home_b2b_f.result()
        if away_b2b_f is not None:
            away_b2b = away_b2b_f.result()

    # Tag each leader with their team info
    for p in home_leaders:
        p["_team"] = home_team
        p["_is_home"] = True
        p["_opp_team_id"] = away_team_id
    for p in away_leaders:
        p["_team"] = away_team
        p["_is_home"] = False
        p["_opp_team_id"] = home_team_id

    all_players = home_leaders + away_leaders

    # Filter out injured-OUT players
    out_names = {s["player_name"].lower() for s in injured_stars
                 if s.get("status", "").lower() == "out"}
    all_players = [p for p in all_players if p["name"].lower() not in out_names]

    if not all_players:
        return results

    league_avg_def = get_league_defensive_average(sport)

    # Pre-map defensive stats by team_id
    def_by_team = {home_team_id: home_def, away_team_id: away_def}

    # ── Fetch all game logs in parallel ──
    with ThreadPoolExecutor(max_workers=_API_WORKERS) as log_pool:
        game_log_futures = {}
        for player in all_players:
            if player.get("ppg", 0) > 0:
                game_log_futures[player["name"]] = log_pool.submit(
                    get_player_game_log, player["name"], count=7, sport=sport
                )

    # Stat types to analyze: (stat_key, season_avg_key, label, odds_key, min_avg)
    stat_configs = [
        ("pts", "ppg", "PTS", "points", 8.0),
        ("reb", "rpg", "REB", "rebounds", 4.0),
        ("ast", "apg", "AST", "assists", 3.0),
    ]

    for player in all_players:
        player_name = player["name"]

        if player.get("ppg", 0) <= 0:
            continue

        # Get opponent defensive stats (already fetched)
        opp_def = def_by_team.get(player["_opp_team_id"])
        opp_def_rating = opp_def.get("pts_allowed_per_game") if opp_def else None

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
            if season_avg < min_avg:
                continue

            posted_line = player_odds.get(odds_key)

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
                "edge": proj["edge"],
                "signal": proj["signal"],
                "confidence": proj["confidence"],
                "streak": proj["streak"],
                "minutes_unstable": proj["minutes_unstable"],
            })

    # Sort by abs(edge) descending
    results.sort(key=lambda x: abs(x["edge"]), reverse=True)
    return results


def get_game_props(event_id, sport="nba"):
    """
    Standalone PRISM analysis for a single game, invoked on-demand.
    Fetches all needed context from ESPN API and runs _run_prism_analysis().

    Returns:
        List of prop signal dicts, or empty list on failure.
    """
    if sport != "nba":
        return []

    # Find the game across today + tomorrow
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

    if not game:
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
            classify_dt = game_dt - timedelta(hours=8)  # PST for NBA
            hour, minute = classify_dt.hour, classify_dt.minute
            day_of_week = classify_dt.strftime("%A")
            slot_type = classify_slot(day_of_week, hour, minute)
        except (ValueError, TypeError):
            pass

    # Parallel fetch: spread, injuries, B2B, O/U, player props odds
    with ThreadPoolExecutor(max_workers=_API_WORKERS) as pool:
        spread_f = pool.submit(get_game_spread, event_id, sport)
        injuries_f = pool.submit(get_all_injuries, sport)
        b2b_home_f = pool.submit(check_back_to_back, home_team_id, game_date_str, sport)
        b2b_away_f = pool.submit(check_back_to_back, away_team_id, game_date_str, sport)
        ou_f = pool.submit(get_game_overunder, event_id, sport=sport)
        props_odds_f = pool.submit(get_player_props_odds, sport)

        opening, current = spread_f.result()
        all_injuries = injuries_f.result()
        home_b2b = b2b_home_f.result()
        away_b2b = b2b_away_f.result()
        game_total = ou_f.result()
        try:
            player_props_lines = props_odds_f.result()
        except Exception:
            player_props_lines = {}

    # Build injured_stars list
    injured_stars = []
    for team_name in [home_team, away_team]:
        for injury in all_injuries.get(team_name, []):
            if injury.get("status", "").lower() == "out":
                pid = injury.get("player_id")
                player_stats = None
                star = False
                star_reason = ""
                if pid:
                    player_stats = get_player_season_averages(pid, sport)
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

    return _run_prism_analysis(
        home_team_id, away_team_id, home_team, away_team,
        event_id, game_date_str, current, slot_type,
        injured_stars, player_props_lines or {},
        sport,
        home_b2b=home_b2b, away_b2b=away_b2b, game_total=game_total,
    )
