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
    get_team_recent_results, get_game_weather_espn,
    get_game_weather_openweather, is_game_stale,
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


# ─── NFL INDOOR STADIUMS ────────────────────────────────────────────────────
# Dome or retractable-roof venues where weather doesn't apply
NFL_INDOOR_STADIUMS = {
    "AT&T Stadium",             # Cowboys
    "Allegiant Stadium",        # Raiders
    "Caesars Superdome",        # Saints
    "Ford Field",               # Lions
    "Lucas Oil Stadium",        # Colts
    "Mercedes-Benz Stadium",    # Falcons
    "NRG Stadium",              # Texans
    "State Farm Stadium",       # Cardinals
    "SoFi Stadium",             # Rams/Chargers
    "U.S. Bank Stadium",        # Vikings
}


# ─── CFB RANK TIERS ──────────────────────────────────────────────────────────
# Frontend (#1-9):  Public perception darlings — NOT expected to cover big spreads
# Backend (#20-25): Under the radar — expected to cover
# Middle (#10-19):  In between — evaluate case by case

def _get_rank_tier(rank):
    """Returns 'frontend', 'middle', 'backend', or None for unranked."""
    if rank is None:
        return None
    if 1 <= rank <= 9:
        return "frontend"
    if 10 <= rank <= 19:
        return "middle"
    if 20 <= rank <= 25:
        return "backend"
    return None


# Expected spread ranges when a ranked team plays an unranked team
CFB_EXPECTED_SPREADS = {
    (1, 5): (24, 28),
    (6, 10): (18, 22),
    (11, 15): (14, 18),
    (16, 20): (10, 14),
    (21, 25): (7, 10),
}

CBB_EXPECTED_SPREADS = {
    (1, 5): (12, 16),
    (6, 10): (9, 12),
    (11, 15): (7, 9),
    (16, 20): (5, 7),
    (21, 25): (3, 5),
}

# Keep backward-compatible alias
EXPECTED_SPREADS = CFB_EXPECTED_SPREADS


def _get_expected_spread(rank, sport="cfb"):
    """Returns (low, high) expected spread for a rank tier, or None."""
    table = CBB_EXPECTED_SPREADS if sport == "cbb" else CFB_EXPECTED_SPREADS
    for (lo, hi), spread_range in table.items():
        if lo <= rank <= hi:
            return spread_range
    return None


def _detect_rank_scam(home_rank, away_rank, current_spread, slot_type):
    """
    Detect Rank Scam: both teams ranked, better-ranked team is at home
    but listed as the underdog (positive home spread).

    Trigger conditions (ALL must be true):
      1. Both teams are ranked
      2. The better-ranked team (lower number) is at home
      3. The better-ranked team is the underdog (positive spread)

    Slot confirmation:
      - Public slot → ranked underdog at home COVERS → take them on the spread
      - Vegas slot  → ranked underdog at home does NOT cover → fade them

    Returns dict with detection results.
    """
    result = {"is_rank_scam": False}

    if current_spread is None:
        return result

    # Both teams must be ranked
    if home_rank is None or away_rank is None:
        return result

    # Better-ranked team (lower number) must be at home
    if home_rank >= away_rank:
        return result

    # Home team must be the underdog (positive spread means home is underdog)
    if current_spread <= 0:
        return result

    # All conditions met — rank scam detected
    result["is_rank_scam"] = True
    result["scam_team"] = "home"
    result["home_rank"] = home_rank
    result["away_rank"] = away_rank
    result["spread"] = current_spread
    result["tier"] = _get_rank_tier(home_rank)

    if slot_type in ("public", "caution"):
        result["scam_action"] = (
            f"#{home_rank} at home as underdog vs #{away_rank} — "
            f"PUBLIC slot: expect them to COVER (+{current_spread})"
        )
    elif slot_type in ("vegas", "trap"):
        result["scam_action"] = (
            f"#{home_rank} at home as underdog vs #{away_rank} — "
            f"VEGAS slot: FADE the home underdog"
        )
    else:
        result["scam_action"] = (
            f"#{home_rank} at home as underdog vs #{away_rank} — "
            f"rank scam detected, investigate"
        )

    return result


def _detect_spread_discrepancy(home_rank, away_rank, current_spread, slot_type, sport="cfb"):
    """
    Detect spread discrepancy when a ranked team plays an unranked team.

    If the actual spread is far below the expected range for the rank tier, flag it.

    Returns dict with detection results.
    """
    result = {"is_discrepancy": False}

    if current_spread is None:
        return result

    # Determine which team is ranked vs unranked
    ranked_team = None
    rank = None
    if home_rank is not None and away_rank is None:
        ranked_team = "home"
        rank = home_rank
        spread_magnitude = abs(current_spread)
    elif away_rank is not None and home_rank is None:
        ranked_team = "away"
        rank = away_rank
        spread_magnitude = abs(current_spread)
    else:
        return result  # Both ranked or both unranked — not applicable

    expected = _get_expected_spread(rank, sport=sport)
    if expected is None:
        return result

    expected_low, expected_high = expected

    # Discrepancy: actual spread is significantly below expected low end
    if spread_magnitude < expected_low - 3:
        result["is_discrepancy"] = True
        result["ranked_team"] = ranked_team
        result["rank"] = rank
        result["expected_range"] = f"{expected_low}-{expected_high}"
        result["actual_spread"] = current_spread

        tier = _get_rank_tier(rank)
        if tier == "frontend":
            result["discrepancy_action"] = f"Line is suspiciously low for #{rank} — frontend team, don't expect cover"
        elif tier == "backend":
            result["discrepancy_action"] = f"Line looks off for #{rank} — backend team, expect cover"
        else:
            result["discrepancy_action"] = f"Spread discrepancy for #{rank} — investigate"

    return result


# ─── NFL ANALYSIS HELPERS ────────────────────────────────────────────────────

def _analyze_nfl_trend_discrepancy(home_team_id, away_team_id):
    """
    Analyzes last 4 games for both teams.
    Struggling teams (1-3 or 0-4) = bounce-back value.
    Hot teams (4-0 or 3-1) = regression risk.

    Returns:
        Dict with trend analysis data.
    """
    result = {"applies": False, "home_signal": None, "away_signal": None}

    home_results = get_team_recent_results(home_team_id, count=4)
    away_results = get_team_recent_results(away_team_id, count=4)

    def classify_trend(results):
        if len(results) < 4:
            return None
        wins = sum(1 for r in results if r["result"] == "W")
        if wins <= 1:
            return "bounce-back"
        elif wins >= 3:
            return "regression"
        return None

    home_signal = classify_trend(home_results)
    away_signal = classify_trend(away_results)

    home_record = ""
    away_record = ""
    if home_results:
        hw = sum(1 for r in home_results if r["result"] == "W")
        home_record = f"{hw}-{len(home_results) - hw}"
    if away_results:
        aw = sum(1 for r in away_results if r["result"] == "W")
        away_record = f"{aw}-{len(away_results) - aw}"

    if home_signal or away_signal:
        result["applies"] = True
        result["home_signal"] = home_signal
        result["away_signal"] = away_signal
        result["home_record"] = home_record
        result["away_record"] = away_record

        # Strong contrarian: one hot + one struggling
        if (home_signal == "bounce-back" and away_signal == "regression") or \
           (home_signal == "regression" and away_signal == "bounce-back"):
            result["strong_contrarian"] = True
        else:
            result["strong_contrarian"] = False

    return result


def _analyze_nfl_overunder(event_id, home_team_id, away_team_id):
    """
    Two checks:
    1. Flag totals above 50.5 as potential under.
    2. Compare total to combined team scoring averages, flag 6+ point divergence.

    Returns:
        Dict with O/U analysis data.
    """
    result = {"applies": False, "flags": []}

    total = get_game_overunder(event_id)
    if total is None:
        return result

    result["total"] = total

    # Check 1: high total
    if total > 50.5:
        result["applies"] = True
        result["flags"].append(f"Total {total} is above 50.5 — lean UNDER")

    # Check 2: compare to team scoring averages
    home_results = get_team_recent_results(home_team_id, count=4)
    away_results = get_team_recent_results(away_team_id, count=4)

    if home_results and away_results:
        home_avg = sum(r["score"] for r in home_results) / len(home_results)
        away_avg = sum(r["score"] for r in away_results) / len(away_results)
        combined_avg = home_avg + away_avg
        divergence = abs(total - combined_avg)

        result["combined_avg"] = round(combined_avg, 1)
        result["divergence"] = round(divergence, 1)

        if divergence >= 6:
            result["applies"] = True
            direction = "OVER" if total < combined_avg else "UNDER"
            result["flags"].append(
                f"Total {total} vs combined avg {result['combined_avg']} "
                f"({result['divergence']} pt gap) — lean {direction}"
            )

    return result


def _analyze_nfl_weather(game, event_id):
    """
    3-tier weather fetch: scoreboard inline → ESPN summary → OpenWeather fallback.
    Skips dome stadiums. Flags wind 15+ mph, temp <=32F, precipitation.

    Returns:
        Dict with weather data and alerts.
    """
    venue_name = game.get("venue_name", "")

    # Check if indoor stadium
    if venue_name in NFL_INDOOR_STADIUMS:
        return {"is_dome": True, "alerts": []}

    result = {"is_dome": False, "alerts": []}

    # Tier 1: inline weather from scoreboard
    weather = game.get("weather")

    # Tier 2: ESPN summary
    if not weather:
        weather = get_game_weather_espn(event_id)

    # Tier 3: OpenWeather fallback
    if not weather:
        city = game.get("venue_city", "")
        state = game.get("venue_state", "")
        if city and state:
            weather = get_game_weather_openweather(city, state)

    if not weather:
        return result

    result["weather"] = weather
    temp = weather.get("temperature")
    wind = weather.get("wind_speed")
    condition = weather.get("condition", "")
    precip = weather.get("precipitation")

    if wind is not None and float(wind) >= 15:
        result["alerts"].append(f"Wind {wind} mph")
    if temp is not None and float(temp) <= 32:
        result["alerts"].append(f"Temp {temp}°F")
    if precip and float(precip) > 0:
        result["alerts"].append(f"Precipitation: {condition}")

    return result


# ─── FEEDBACK LOOP CACHE ────────────────────────────────────────────────────
_feedback_cache = {}
_FEEDBACK_TTL = 300  # 5 minutes


def _get_feedback_adjustment(slot_type, sport):
    """
    Returns a flat score adjustment (-2 to +3) based on historical ledger performance
    for this slot type and sport. Cached at module level with 5-min TTL.
    """
    import time
    cache_key = f"{sport}:{slot_type}"
    now = time.time()

    entry = _feedback_cache.get(cache_key)
    if entry and (now - entry["ts"]) < _FEEDBACK_TTL:
        return entry["adj"]

    try:
        perf = tracker.get_factor_performance(sport)
    except Exception:
        perf = None

    adj = 0
    if perf:
        # Slot-level adjustment
        slot_data = perf.get("by_slot", {}).get(slot_type)
        if slot_data and slot_data["total"] >= 20:
            if slot_data["rate"] > 60:
                adj += 2
            elif slot_data["rate"] < 45:
                adj -= 2

        # Overall sport adjustment
        overall = perf.get("overall", {})
        if overall.get("total", 0) >= 50:
            if overall["rate"] > 58:
                adj += 1
            elif overall["rate"] < 45:
                adj -= 1

    # Clamp to [-2, +3]
    adj = max(-2, min(3, adj))

    _feedback_cache[cache_key] = {"adj": adj, "ts": now}
    return adj


def _analyze_ats_record(lean_team, sport):
    """
    Checks our ledger for the lean team's ATS record.

    +4 if >60% ATS (min 3 decided games)
    -3 if <40% ATS

    Returns:
        Dict with ats_bonus, ats_penalty, and detail.
    """
    result = {"ats_bonus": False, "ats_penalty": False, "detail": ""}

    if not lean_team:
        return result

    try:
        record = tracker.get_team_ats_record(lean_team, sport)
    except Exception:
        return result

    if record is None:
        return result

    if record["rate"] > 60:
        result["ats_bonus"] = True
        result["detail"] = (
            f"{lean_team} ATS: {record['wins']}-{record['losses']} "
            f"({record['rate']}%)"
        )
    elif record["rate"] < 40:
        result["ats_penalty"] = True
        result["detail"] = (
            f"{lean_team} ATS: {record['wins']}-{record['losses']} "
            f"({record['rate']}%)"
        )

    return result


def _analyze_public_betting(odds_data, home_team, away_team, lean_team, slot_type):
    """
    Compares Pinnacle (sharp) spread vs consensus as proxy for sharp vs public money.

    +5: Pinnacle disagrees with consensus by 1.5+ pts AND aligns with lean (vegas slot)
    +3: Sharp + public align with lean (public slot)

    Returns:
        Dict with public_betting_bonus (int 0/3/5) and detail.
    """
    from api_client import _match_odds_to_game

    result = {"public_betting_bonus": 0, "detail": ""}

    if not odds_data or not lean_team:
        return result

    match = _match_odds_to_game(odds_data, home_team, away_team)
    if match is None or match.get("pinnacle_spread") is None:
        return result

    pinnacle = match["pinnacle_spread"]
    consensus = match["consensus_spread"]
    diff = abs(pinnacle - consensus)

    # Determine which team Pinnacle favors more than consensus
    # More negative = more home-favored
    lean_is_home = (lean_team == home_team)

    if slot_type in ("vegas", "trap") and diff >= 1.5:
        # Sharp divergence in vegas slot — check if Pinnacle aligns with lean
        # If lean is home: pinnacle more negative (more home-favored) = aligns
        # If lean is away: pinnacle more positive (less home-favored) = aligns
        if lean_is_home and pinnacle < consensus:
            result["public_betting_bonus"] = 5
            result["detail"] = (
                f"Sharp divergence: Pinnacle {pinnacle:+.1f} vs consensus "
                f"{consensus:+.1f} — favors {lean_team}"
            )
        elif not lean_is_home and pinnacle > consensus:
            result["public_betting_bonus"] = 5
            result["detail"] = (
                f"Sharp divergence: Pinnacle {pinnacle:+.1f} vs consensus "
                f"{consensus:+.1f} — favors {lean_team}"
            )
    elif slot_type in ("public", "caution") and diff < 1.5:
        # Sharp and public aligned — check if both align with lean
        # consensus negative = home favored
        if lean_is_home and consensus < 0:
            result["public_betting_bonus"] = 3
            result["detail"] = (
                f"Sharp + public aligned: consensus {consensus:+.1f} "
                f"— backs {lean_team}"
            )
        elif not lean_is_home and consensus > 0:
            result["public_betting_bonus"] = 3
            result["detail"] = (
                f"Sharp + public aligned: consensus {consensus:+.1f} "
                f"— backs {lean_team}"
            )

    return result


def _analyze_back_to_back(home_team_id, away_team_id, game_date_str,
                          lean_team, home_team, away_team, sport="nba"):
    """
    Back-to-back detection for NBA and NHL.

    Returns:
        Dict with b2b_bonus (bool) and b2b_penalty (bool), plus detail string.
    """
    result = {"b2b_bonus": False, "b2b_penalty": False, "detail": ""}

    if sport not in ("nba", "nhl"):
        return result
    if not home_team_id or not away_team_id or not lean_team:
        return result

    home_b2b = check_back_to_back(home_team_id, game_date_str, sport)
    away_b2b = check_back_to_back(away_team_id, game_date_str, sport)

    lean_is_home = (lean_team == home_team)
    lean_b2b = home_b2b if lean_is_home else away_b2b
    opp_b2b = away_b2b if lean_is_home else home_b2b
    opp_name = away_team if lean_is_home else home_team

    if opp_b2b and not lean_b2b:
        result["b2b_bonus"] = True
        result["detail"] = f"{opp_name} on B2B — rest advantage for {lean_team}"
    elif lean_b2b and not opp_b2b:
        result["b2b_penalty"] = True
        result["detail"] = f"{lean_team} on B2B — fatigue risk"

    return result


# Revenge game thresholds by sport
H2H_REVENGE_THRESHOLDS = {
    "nba": 10,
    "nhl": 3,
    "cfb": 10,
    "cbb": 10,
    "nfl": 7,
}


def _analyze_head_to_head(home_team_id, lean_team, home_team, away_team, sport="nba"):
    """
    Head-to-head / revenge game analysis.

    +3 if lean team lost prior matchup by threshold+ (revenge motivation)
    +2 if lean team dominated prior matchup (continued dominance)

    Returns:
        Dict with h2h_revenge_bonus, h2h_dominance_bonus, and detail.
    """
    result = {"h2h_revenge_bonus": False, "h2h_dominance_bonus": False, "detail": ""}

    if not home_team_id or not lean_team:
        return result

    lean_is_home = (lean_team == home_team)
    opponent_name = away_team if lean_is_home else home_team
    team_id = home_team_id  # We check from home team's perspective

    matchup = get_previous_matchup(team_id, opponent_name, sport)
    if matchup is None:
        return result

    threshold = H2H_REVENGE_THRESHOLDS.get(sport, 10)
    margin = matchup["margin"]

    # margin is from home_team's perspective
    if lean_is_home:
        lean_margin = margin
    else:
        lean_margin = -margin

    if lean_margin < 0 and abs(lean_margin) >= threshold:
        result["h2h_revenge_bonus"] = True
        result["detail"] = (
            f"REVENGE — {lean_team} lost by {abs(lean_margin)} "
            f"({matchup['team_score']}-{matchup['opp_score']}) last meeting"
        )
    elif lean_margin > 0 and lean_margin >= threshold:
        result["h2h_dominance_bonus"] = True
        result["detail"] = (
            f"PRIOR WIN — {lean_team} won by {lean_margin} "
            f"({matchup['team_score']}-{matchup['opp_score']}) last meeting"
        )

    return result


def _analyze_home_away_split(lean_team, home_team, slot_type, current_spread):
    """
    +3 bonus when the lean aligns with the natural home/away edge:
      - Public slot + lean is home favorite
      - Vegas slot + lean is road underdog

    Returns:
        bool: True if the bonus applies.
    """
    if lean_team is None or current_spread is None:
        return False

    is_lean_home = (lean_team == home_team)
    is_home_fav = (current_spread < 0)

    if slot_type in ("public", "caution"):
        # Public: bonus when lean is home AND home is favored
        return is_lean_home and is_home_fav
    elif slot_type in ("vegas", "trap"):
        # Vegas: bonus when lean is away AND away is underdog (home favored)
        return (not is_lean_home) and is_home_fav

    return False


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

    # Fetch player props odds once for PRISM (NBA only, graceful)
    player_props_lines = {}
    if sport == "nba":
        try:
            player_props_lines = get_player_props_odds(sport)
        except Exception:
            player_props_lines = {}

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
            player_props_lines=player_props_lines,
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
                          player_props_lines=None, lightweight=False):
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
    lean_team = _determine_lean(slot_type, home_team, away_team, current_spread)

    # Trell Rule lean override
    if trell_result.get("applies"):
        trell_team = trell_result.get("star_team")
        if trell_team:
            lean_team = trell_team

    # ── Collect Phase 1b parallel results + compute factors ──────────
    b2b_result = {"b2b_bonus": False, "b2b_penalty": False, "detail": ""}
    h2h_result = {"h2h_revenge_bonus": False, "h2h_dominance_bonus": False, "detail": ""}
    nfl_trend = {"applies": False}
    nfl_overunder = {"applies": False}
    nfl_weather = {"is_dome": False, "alerts": []}
    ats_result = {"ats_bonus": False, "ats_penalty": False, "detail": ""}
    public_betting_result = {"public_betting_bonus": 0, "detail": ""}
    feedback_adj = 0
    player_props = []

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

        # PRISM Player Props (NBA only)
        if sport == "nba" and home_team_id and away_team_id:
            player_props = _run_prism_analysis(
                home_team_id, away_team_id, home_team, away_team,
                event_id, game_date_str, current_spread, slot_type,
                injured_stars, player_props_lines or {},
                sport,
            )

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
    )
    if sport == "nfl":
        max_score = 53
    elif sport in ("cfb", "cbb"):
        max_score = 48
    else:
        max_score = 42
    cover_pct = round(50 + (score / max_score) * 45, 1)

    # Recommendation label
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

    # Include PRISM player props (NBA)
    if player_props:
        result["player_props"] = player_props

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

    return result


def _run_prism_analysis(home_team_id, away_team_id, home_team, away_team,
                        event_id, game_date_str, current_spread, slot_type,
                        injured_stars, player_props_lines, sport):
    """
    Runs PRISM player prop analysis for a single game.
    Gets roster leaders, game logs, defensive stats, and generates projections.

    Returns:
        List of prop signal dicts sorted by abs(edge) descending,
        filtered to non-PASS signals only.
    """
    results = []

    # ── Fire roster leaders, O/U, B2B, and defensive stats all in parallel ──
    with ThreadPoolExecutor(max_workers=_API_WORKERS) as prism_pool:
        home_leaders_f = prism_pool.submit(get_team_roster_leaders, home_team_id, sport=sport, limit=2)
        away_leaders_f = prism_pool.submit(get_team_roster_leaders, away_team_id, sport=sport, limit=2)
        game_total_f = prism_pool.submit(get_game_overunder, event_id, sport=sport)
        home_b2b_f = prism_pool.submit(check_back_to_back, home_team_id, game_date_str, sport)
        away_b2b_f = prism_pool.submit(check_back_to_back, away_team_id, game_date_str, sport)
        home_def_f = prism_pool.submit(get_team_defensive_stats, home_team_id, sport=sport)
        away_def_f = prism_pool.submit(get_team_defensive_stats, away_team_id, sport=sport)

        home_leaders = home_leaders_f.result()
        away_leaders = away_leaders_f.result()
        game_total = game_total_f.result()
        home_b2b = home_b2b_f.result()
        away_b2b = away_b2b_f.result()
        home_def = home_def_f.result()
        away_def = away_def_f.result()

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

    for player in all_players:
        player_name = player["name"]
        season_ppg = player.get("ppg", 0)

        if season_ppg <= 0:
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

        # Get posted line from odds (normalized name match)
        posted_line = None
        norm_name = player_name.strip().lower()
        if norm_name in player_props_lines:
            posted_line = player_props_lines[norm_name].get("points")

        proj = calculate_prism_projection(
            season_avg=season_ppg,
            recent_games=recent_games or [],
            stat_type="pts",
            opponent_def_rating=opp_def_rating,
            league_avg_def=league_avg_def,
            game_total=game_total,
            is_b2b=is_b2b,
            is_home=player["_is_home"],
            spread=current_spread,
            injured_teammates=injured_teammates,
            posted_line=posted_line,
            slot_type=slot_type,
            sport=sport,
        )

        if proj is None:
            continue

        if proj["signal"] == "PASS":
            continue

        results.append({
            "player_name": player_name,
            "team": team_name,
            "stat_type": "PTS",
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


def _fmt_spread(val):
    """Format a spread value with +/- sign."""
    if val > 0:
        return "+" + str(val)
    return str(val)


def _determine_lean(slot_type, home_team, away_team, current_spread):
    """
    Determine which team to lean towards based on slot type and spread.

    Public/caution slot -> lean favorite (public money tends to be right).
    Vegas/trap slot -> lean underdog (sharp money fades the public).
    Negative spread = home team favored.
    """
    if current_spread is None:
        return None

    if slot_type in ("public", "caution"):
        # Lean with the favorite (expect sensible/public outcome)
        return home_team if current_spread < 0 else away_team
    elif slot_type in ("vegas", "trap"):
        # Lean with the underdog (against public / trap game)
        return away_team if current_spread < 0 else home_team

    return None


def _calculate_score(slot_type, line_confirms, trell_applies,
                     line_magnitude=0.0,
                     rank_scam_applies=False, spread_disc_applies=False,
                     trend_disc_applies=False, ou_disc_applies=False,
                     weather_applies=False,
                     spread_value=None, sport="nba",
                     b2b_bonus=False, b2b_penalty=False,
                     ats_bonus=False, ats_penalty=False,
                     home_away_applies=False,
                     public_betting_bonus=0,
                     feedback_adjustment=0,
                     h2h_revenge_bonus=False, h2h_dominance_bonus=False):
    """
    Scoring:
      +10  public slot
      +0-8 line movement confirms slot (graduated by magnitude)
      +5   trell rule confirms
      +5   rank scam detected (CFB/CBB)
      +5   spread discrepancy detected (CFB/CBB)
      +5   trend discrepancy (NFL)
      +5   O/U discrepancy (NFL)
      +5   weather factor (NFL)
      -3   spread size penalty (large spreads are harder to cover)
      +4/-3 back-to-back rest (NBA/NHL)
      +4/-3 ATS record (all)
      +3   home/away split (all)
      +3/+5 public betting / sharp money (all)
      -2/+3 feedback loop (all)
      +3/+2 head-to-head revenge/dominance (all)
      = 42 max (NBA/NHL), 48 max (CFB/CBB), 53 max (NFL)

    Returns:
        (total_score, breakdown_dict)
    """
    breakdown = {"slot": 0, "line_movement": 0, "trell": 0,
                 "rank_scam": 0, "spread_discrepancy": 0,
                 "trend_discrepancy": 0, "overunder": 0, "weather": 0,
                 "spread_penalty": 0,
                 "b2b": 0, "ats_record": 0, "home_away_split": 0,
                 "public_betting": 0, "feedback": 0, "head_to_head": 0}

    if slot_type == "public":
        breakdown["slot"] = 10
    if line_confirms:
        breakdown["line_movement"] = score_line_movement(line_magnitude)
    if trell_applies:
        breakdown["trell"] = 5
    if rank_scam_applies:
        breakdown["rank_scam"] = 5
    if spread_disc_applies:
        breakdown["spread_discrepancy"] = 5
    if trend_disc_applies:
        breakdown["trend_discrepancy"] = 5
    if ou_disc_applies:
        breakdown["overunder"] = 5
    if weather_applies:
        breakdown["weather"] = 5

    # New factors
    if b2b_bonus:
        breakdown["b2b"] = 4
    elif b2b_penalty:
        breakdown["b2b"] = -3
    if ats_bonus:
        breakdown["ats_record"] = 4
    elif ats_penalty:
        breakdown["ats_record"] = -3
    if home_away_applies:
        breakdown["home_away_split"] = 3
    breakdown["public_betting"] = public_betting_bonus
    breakdown["feedback"] = feedback_adjustment
    if h2h_revenge_bonus:
        breakdown["head_to_head"] = 3
    elif h2h_dominance_bonus:
        breakdown["head_to_head"] = 2

    # Spread size penalty: large spreads are harder to cover
    if spread_value is not None:
        spread_abs = abs(spread_value)
        if sport == "nfl" and spread_abs > 10:
            breakdown["spread_penalty"] = -3
        elif sport in ("nba", "nhl") and spread_abs > 8:
            breakdown["spread_penalty"] = -3
        elif sport in ("cfb", "cbb") and spread_abs > 14:
            breakdown["spread_penalty"] = -3

    total = sum(breakdown.values())
    total = max(total, 0)
    return total, breakdown
