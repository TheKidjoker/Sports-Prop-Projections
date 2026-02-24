# ─── Analysis Factors & Scoring ────────────────────────────────────────────────
# All prediction factors, score calculation, lean determination, and NFL helpers.

import time
import tracker
from api_client import (
    get_game_overunder, get_team_recent_results,
    get_game_weather_espn, get_game_weather_openweather,
    check_back_to_back, get_previous_matchup,
)
from api_odds import _match_odds_to_game
from line_movement import score_line_movement


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


def _detect_vegas_trap(slot_type, current_spread, home_team_id, away_team_id,
                       home_team, away_team):
    """
    Detects classic NBA trap games: heavy favorite in a vegas/trap slot
    where the favorite is cold. Public bets the name, underdog covers.

    Conditions:
      - Vegas or trap slot
      - |spread| >= 7 (heavy favorite)
      - Favorite cold: <= 2 wins in last 7

    Bonus:
      +5 if favorite is cold
      +7 if both teams are cold (strongest signal)

    Returns:
        Dict with is_vegas_trap, bonus, detail, fav_record.
    """
    result = {"is_vegas_trap": False, "bonus": 0, "detail": "", "fav_record": ""}

    if slot_type not in ("vegas", "trap"):
        return result
    if current_spread is None or abs(current_spread) < 7:
        return result

    # Identify favorite and underdog
    # Negative spread = home favored
    if current_spread < 0:
        fav_team_id, fav_team = home_team_id, home_team
        dog_team_id, dog_team = away_team_id, away_team
        dog_spread = abs(current_spread)
    else:
        fav_team_id, fav_team = away_team_id, away_team
        dog_team_id, dog_team = home_team_id, home_team
        dog_spread = abs(current_spread)

    if not fav_team_id:
        return result

    # Check favorite's last 7 games
    fav_results = get_team_recent_results(fav_team_id, count=7, sport="nba")
    if not fav_results or len(fav_results) < 5:
        return result

    fav_wins = sum(1 for r in fav_results if r["result"] == "W")
    fav_record = f"{fav_wins}-{len(fav_results) - fav_wins}"

    if fav_wins > 2:
        return result

    # Favorite is cold — check underdog too
    bonus = 5
    detail = (f"Heavy favorite ({fav_team} -{dog_spread}) on a cold streak "
              f"({fav_record} L7) — take {dog_team} +{dog_spread}")

    if dog_team_id:
        dog_results = get_team_recent_results(dog_team_id, count=7, sport="nba")
        if dog_results and len(dog_results) >= 5:
            dog_wins = sum(1 for r in dog_results if r["result"] == "W")
            if dog_wins <= 2:
                bonus = 7
                dog_record = f"{dog_wins}-{len(dog_results) - dog_wins}"
                detail = (f"Both teams cold — {fav_team} ({fav_record}) favored by "
                          f"{dog_spread} vs {dog_team} ({dog_record}) — take {dog_team} +{dog_spread}")

    result["is_vegas_trap"] = True
    result["bonus"] = bonus
    result["detail"] = detail
    result["fav_record"] = fav_record

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


def _fmt_spread(val):
    """Format a spread value with +/- sign."""
    if val > 0:
        return "+" + str(val)
    return str(val)


def _determine_lean(slot_type, home_team, away_team, current_spread, sport="nba"):
    """
    Determine which team to lean towards based on slot type and spread.

    NBA (backtested): always lean underdog regardless of slot — the public
    inflates favorite lines in all time slots, creating underdog value.

    Other sports:
      Public/caution slot -> lean favorite (public money tends to be right).
      Vegas/trap slot -> lean underdog (sharp money fades the public).

    Negative spread = home team favored.
    """
    if current_spread is None:
        return None

    if sport == "nba":
        # NBA: lean underdog in all slots (backtested +17.5% ROI)
        return away_team if current_spread < 0 else home_team

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
                     h2h_revenge_bonus=False, h2h_dominance_bonus=False,
                     vegas_trap_bonus=0):
    """
    Scoring (NBA backtested adjustments noted with *):
      +10/+5*  public slot (NBA: +5, others: +10)
      +0-8/+0-5*  line movement confirms slot (NBA: reduced weights)
      +5   trell rule confirms
      +5   rank scam detected (CFB/CBB)
      +5   spread discrepancy detected (CFB/CBB)
      +5   trend discrepancy (NFL)
      +5   O/U discrepancy (NFL)
      +5   weather factor (NFL)
      -3/0*  spread size penalty (NBA: removed — large spreads cover well)
      +4/-3 or +2/-1*  back-to-back rest (NBA: reduced, others: original)
      +4/-3 ATS record (all)
      +3   home/away split (all)
      +3/+5 public betting / sharp money (all)
      -2/+3 feedback loop (all)
      +3/+2 or +1*/+2  head-to-head (NBA: revenge reduced to +1)
      +5/+7 vegas trap (NBA only)
      = 39 max (NBA), 42 max (NHL), 48 max (CFB/CBB), 53 max (NFL)

    Returns:
        (total_score, breakdown_dict)
    """
    breakdown = {"slot": 0, "line_movement": 0, "trell": 0,
                 "rank_scam": 0, "spread_discrepancy": 0,
                 "trend_discrepancy": 0, "overunder": 0, "weather": 0,
                 "spread_penalty": 0,
                 "b2b": 0, "ats_record": 0, "home_away_split": 0,
                 "public_betting": 0, "feedback": 0, "head_to_head": 0,
                 "vegas_trap": 0}

    if slot_type == "public":
        breakdown["slot"] = 5 if sport == "nba" else 10
    if line_confirms:
        breakdown["line_movement"] = score_line_movement(line_magnitude, sport=sport)
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

    # B2B: NBA uses reduced weights (backtested — minimal lift)
    if b2b_bonus:
        breakdown["b2b"] = 2 if sport == "nba" else 4
    elif b2b_penalty:
        breakdown["b2b"] = -1 if sport == "nba" else -3
    if ats_bonus:
        breakdown["ats_record"] = 4
    elif ats_penalty:
        breakdown["ats_record"] = -3
    if home_away_applies:
        breakdown["home_away_split"] = 3
    breakdown["public_betting"] = public_betting_bonus
    breakdown["feedback"] = feedback_adjustment
    # H2H: NBA revenge reduced (backtested — negative lift)
    if h2h_revenge_bonus:
        breakdown["head_to_head"] = 1 if sport == "nba" else 3
    elif h2h_dominance_bonus:
        breakdown["head_to_head"] = 2
    breakdown["vegas_trap"] = vegas_trap_bonus

    # Spread size penalty: NBA removed (backtested — large spreads cover well in vegas)
    if spread_value is not None and sport != "nba":
        spread_abs = abs(spread_value)
        if sport == "nfl" and spread_abs > 10:
            breakdown["spread_penalty"] = -3
        elif sport == "nhl" and spread_abs > 8:
            breakdown["spread_penalty"] = -3
        elif sport in ("cfb", "cbb") and spread_abs > 14:
            breakdown["spread_penalty"] = -3

    total = sum(breakdown.values())
    total = max(total, 0)
    return total, breakdown
