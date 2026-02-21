from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from api_client import (
    get_todays_games, get_all_injuries, get_game_spread,
    get_player_season_averages, get_game_overunder,
    get_team_recent_results, get_game_weather_espn,
    get_game_weather_openweather, is_game_stale,
)
from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot, score_line_movement
from trell_rule import is_star_player, is_recent_injury, evaluate_trell_rule


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


def scan_all_games(sport="nba", date_str=None):
    """
    Fetch all today's games, analyze each, return ranked list.

    Args:
        sport: "nba", "nhl", "cfb", or "nfl"
        date_str: Optional YYYYMMDD to fetch a specific date.

    Returns:
        List of analysis dicts sorted by confirmation_score descending.
    """
    games = get_todays_games(sport, date_str=date_str)

    # Next-day fallback: if no games or all stale/final, try tomorrow
    if not date_str:
        all_done = (
            not games
            or all(
                is_game_stale(g.get("game_date", ""))
                or g.get("game_status") == "STATUS_FINAL"
                for g in games
            )
        )
        if all_done:
            tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y%m%d")
            games = get_todays_games(sport, date_str=tomorrow)

    if not games:
        return []

    all_injuries = get_all_injuries(sport)

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
        return _analyze_single_game(
            game, day_of_week, all_injuries, is_first_game,
            sport=sport, total_games_on_slate=total_games, game_index=i,
            is_last_sunday_game=is_last_sunday,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_analyze_game_wrapper, enumerate(sorted_games)))

    # Sort by confirmation_score descending
    results.sort(key=lambda r: r.get("confirmation_score", 0), reverse=True)
    return results


def _analyze_single_game(game, day_of_week, all_injuries, is_first_game,
                          sport="nba", total_games_on_slate=1, game_index=0,
                          is_last_sunday_game=False):
    """
    Returns analysis dict for one game.
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
            "game_time_est": game_time_est,
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

    # Line movement
    opening, current = get_game_spread(event_id, sport)
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

    # Trell Rule: check injuries for both teams
    injured_stars = []
    for team_name in [home_team, away_team]:
        team_injuries = all_injuries.get(team_name, [])
        for injury in team_injuries:
            if injury.get("status", "").lower() != "out":
                continue

            recent = is_recent_injury(injury.get("injury_date", ""))
            player_id = injury.get("player_id")

            player_stats = None
            star = False
            star_reason = ""

            if player_id:
                player_stats = get_player_season_averages(player_id, sport)
                if player_stats:
                    star, star_reason = is_star_player(player_stats, sport)

            injured_stars.append({
                "player_name": injury["player_name"],
                "is_star": star,
                "star_reason": star_reason,
                "is_recent": recent,
                "status": injury["status"],
            })

    trell_result = evaluate_trell_rule(injured_stars, slot_type)

    # CFB Rank Scam + Spread Discrepancy detection
    rank_scam = {"is_rank_scam": False}
    spread_discrepancy = {"is_discrepancy": False}
    home_rank = game.get("home_rank")
    away_rank = game.get("away_rank")

    if sport in ("cfb", "cbb"):
        rank_scam = _detect_rank_scam(home_rank, away_rank, current, slot_type)
        spread_discrepancy = _detect_spread_discrepancy(home_rank, away_rank, current, slot_type, sport=sport)

    # Moneyline rule — sport-specific thresholds
    # NBA: 6+ (3-5 pt favorites have terrible ML juice)
    # NFL: 3+ (field goal margin is meaningful)
    # CFB: 7+ (touchdown margin)
    # NHL: never (puck line sport, ML doesn't apply the same way)
    moneyline_recommend = False
    current_spread = current
    ml_threshold = {"nba": 6, "nfl": 3, "cfb": 7, "cbb": 7}.get(sport)
    if opening is not None and current is not None and ml_threshold:
        if abs(current) >= ml_threshold:
            moneyline_recommend = True

    # NFL-specific analyses (vegas/late Sunday only for trend + O/U)
    nfl_trend = {"applies": False}
    nfl_overunder = {"applies": False}
    nfl_weather = {"is_dome": False, "alerts": []}

    if sport == "nfl":
        home_team_id = game.get("home_team_id")
        away_team_id = game.get("away_team_id")

        # Trend + O/U only in vegas slots
        if slot_type == "vegas" and home_team_id and away_team_id:
            nfl_trend = _analyze_nfl_trend_discrepancy(home_team_id, away_team_id)
            nfl_overunder = _analyze_nfl_overunder(event_id, home_team_id, away_team_id)

        # Weather for all non-skip games
        nfl_weather = _analyze_nfl_weather(game, event_id)

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
    )
    if sport == "nfl":
        max_score = 38
    elif sport in ("cfb", "cbb"):
        max_score = 33
    else:
        max_score = 23
    cover_pct = round(50 + (score / max_score) * 45, 1)

    # Determine which team to lean towards
    lean_team = _determine_lean(slot_type, home_team, away_team, current_spread)

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
        "game_time_est": game_time_est,
        "confirmation_score": score,
        "cover_pct": cover_pct,
        "lean_team": lean_team,
        "action": action,
        "recommendation": recommendation,
        "current_spread": current_spread,
    }

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

    return result


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
                     spread_value=None, sport="nba"):
    """
    Scoring:
      +10  public slot
      +0-8 line movement confirms slot (graduated by magnitude)
      +5   trell rule confirms
      +5   rank scam detected (CFB)
      +5   spread discrepancy detected (CFB)
      +5   trend discrepancy (NFL)
      +5   O/U discrepancy (NFL)
      +5   weather factor (NFL)
      -3   spread size penalty (large spreads are harder to cover)
      = 23 max (NBA/NHL), 33 max (CFB), 38 max (NFL)

    Returns:
        (total_score, breakdown_dict)
    """
    breakdown = {"slot": 0, "line_movement": 0, "trell": 0,
                 "rank_scam": 0, "spread_discrepancy": 0,
                 "trend_discrepancy": 0, "overunder": 0, "weather": 0,
                 "spread_penalty": 0}

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
