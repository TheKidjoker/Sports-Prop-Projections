# ─── Analysis Factors & Scoring ────────────────────────────────────────────────
# All prediction factors, score calculation, lean determination, and NFL helpers.

import time
import threading
import tracker
from api_client import (
    get_game_overunder, get_team_recent_results,
    get_game_weather_espn, get_game_weather_openweather,
    check_back_to_back, get_previous_matchup,
)
from api_odds import _match_odds_to_game
from line_movement import score_line_movement
from constants import get_override, UNIVERSAL_DEFAULTS, NBA_UNVALIDATED_CAPS, CBB_UNVALIDATED_CAPS


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


_OU_THRESHOLDS = {
    "nfl": {"high_total": 50.5, "divergence": 6, "recent_count": 4},
    "nba": {"high_total": 230, "divergence": 10, "recent_count": 5},
    "cbb": {"high_total": 155, "divergence": 8, "recent_count": 5},
    "nhl": {"high_total": 6.5, "divergence": 1.0, "recent_count": 5},
    "cfb": {"high_total": 58, "divergence": 7, "recent_count": 4},
}


def _analyze_overunder(event_id, home_team_id, away_team_id, sport="nfl"):
    """
    Two checks:
    1. Flag totals above sport-specific high threshold as potential under.
    2. Compare total to combined team scoring averages, flag divergence.

    Returns:
        Dict with O/U analysis data.
    """
    result = {"applies": False, "flags": []}
    thresholds = _OU_THRESHOLDS.get(sport, _OU_THRESHOLDS["nfl"])

    total = get_game_overunder(event_id, sport)
    if total is None:
        return result

    result["total"] = total

    # Check 1: high total
    if total > thresholds["high_total"]:
        result["applies"] = True
        result["flags"].append(f"Total {total} is above {thresholds['high_total']} — lean UNDER")

    # Check 2: compare to team scoring averages
    recent_count = thresholds["recent_count"]
    home_results = get_team_recent_results(home_team_id, count=recent_count, sport=sport)
    away_results = get_team_recent_results(away_team_id, count=recent_count, sport=sport)

    if home_results and away_results:
        home_avg = sum(r["score"] for r in home_results) / len(home_results)
        away_avg = sum(r["score"] for r in away_results) / len(away_results)
        combined_avg = home_avg + away_avg
        divergence = abs(total - combined_avg)

        result["combined_avg"] = round(combined_avg, 1)
        result["divergence"] = round(divergence, 1)

        if divergence >= thresholds["divergence"]:
            result["applies"] = True
            direction = "OVER" if total < combined_avg else "UNDER"
            result["flags"].append(
                f"Total {total} vs combined avg {result['combined_avg']} "
                f"({result['divergence']} pt gap) — lean {direction}"
            )

    return result


def _analyze_nfl_overunder(event_id, home_team_id, away_team_id):
    """Legacy wrapper for NFL-only callers."""
    return _analyze_overunder(event_id, home_team_id, away_team_id, sport="nfl")


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


# ─── MLB WEATHER ANALYSIS ──────────────────────────────────────────────────

MLB_OPEN_AIR_PARKS = {
    "Wrigley Field",           # Cubs
    "Fenway Park",             # Red Sox
    "Kauffman Stadium",        # Royals
    "Oracle Park",             # Giants
    "Citi Field",              # Mets
    "Dodger Stadium",          # Dodgers
    "Yankee Stadium",          # Yankees
    "Petco Park",              # Padres
    "Great American Ball Park",  # Reds
    "PNC Park",                # Pirates
    "Nationals Park",          # Nationals
    "Oriole Park at Camden Yards",  # Orioles
    "Progressive Field",       # Guardians
    "Guaranteed Rate Field",   # White Sox
    "Target Field",            # Twins
    "Busch Stadium",           # Cardinals
    "Comerica Park",           # Tigers
    "Angel Stadium",           # Angels
    "Oakland Coliseum",        # Athletics
    "Citizens Bank Park",      # Phillies
}

MLB_RETRACTABLE_PARKS = {
    "Globe Life Field",        # Rangers
    "T-Mobile Park",           # Mariners
    "Minute Maid Park",        # Astros
    "loanDepot park",          # Marlins
    "American Family Field",   # Brewers
    "Chase Field",             # Diamondbacks
    "Rogers Centre",           # Blue Jays
}

MLB_DOME_PARKS = {
    "Tropicana Field",         # Rays
}

MLB_HIGH_ALTITUDE_PARKS = {
    "Coors Field": {"altitude_ft": 5280, "run_factor": 1.15},
}


def _analyze_mlb_weather(game, event_id):
    """
    MLB weather analysis with 3-tier fetch (same pattern as NFL).
    MLB-specific thresholds:
      - Wind >= 12 mph: affects fly balls
      - Temp >= 90F: ball carries further, lean offense
      - Temp <= 45F: ball doesn't carry, lean defense
      - Any precipitation: game impact
      - Altitude factor for Coors Field

    Returns:
        Dict with is_dome, alerts, weather, altitude_factor.
    """
    venue_name = game.get("venue_name", "")

    # Check if dome or retractable roof
    if venue_name in MLB_DOME_PARKS or venue_name in MLB_RETRACTABLE_PARKS:
        result = {"is_dome": True, "alerts": []}
        # Still check altitude even for retractable (Coors is open-air though)
        if venue_name in MLB_HIGH_ALTITUDE_PARKS:
            alt_data = MLB_HIGH_ALTITUDE_PARKS[venue_name]
            result["altitude_factor"] = alt_data
            result["alerts"].append(
                f"High Altitude ({alt_data['altitude_ft']}ft) — "
                f"run factor {alt_data['run_factor']}x, lean OVER"
            )
        return result

    result = {"is_dome": False, "alerts": []}

    # Check altitude first (always applies for open-air)
    if venue_name in MLB_HIGH_ALTITUDE_PARKS:
        alt_data = MLB_HIGH_ALTITUDE_PARKS[venue_name]
        result["altitude_factor"] = alt_data
        result["alerts"].append(
            f"High Altitude ({alt_data['altitude_ft']}ft) — "
            f"run factor {alt_data['run_factor']}x, lean OVER"
        )

    # Skip weather fetch for non-open-air parks not in our list
    # (they might be unlisted retractable or new parks)
    if venue_name and venue_name not in MLB_OPEN_AIR_PARKS and venue_name not in MLB_HIGH_ALTITUDE_PARKS:
        return result

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

    # MLB-specific thresholds (lower wind threshold than NFL)
    if wind is not None and float(wind) >= 12:
        result["alerts"].append(f"Wind {wind} mph — affects fly balls")
    if temp is not None and float(temp) >= 90:
        result["alerts"].append(f"Temp {temp}°F — ball carries, lean offense")
    if temp is not None and float(temp) <= 45:
        result["alerts"].append(f"Temp {temp}°F — cold, lean defense")
    if precip and float(precip) > 0:
        result["alerts"].append(f"Precipitation: {condition}")

    return result


# ─── FEEDBACK LOOP CACHE ────────────────────────────────────────────────────
_feedback_cache = {}
_feedback_lock = threading.Lock()
_FEEDBACK_TTL = 300  # 5 minutes
_FEEDBACK_MAX_SIZE = 50  # Bound cache size to prevent unbounded growth


def _get_feedback_adjustment(slot_type, sport):
    """
    Returns a flat score adjustment (-2 to +3) based on historical ledger performance
    for this slot type and sport. Cached at module level with 5-min TTL.
    """
    # NBA feedback loop zeroed permanently — circular dependency, unvalidated
    if sport == "nba":
        return 0

    cache_key = f"{sport}:{slot_type}"
    now = time.time()

    with _feedback_lock:
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
        if slot_data and slot_data["total"] >= 40:
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

    with _feedback_lock:
        _feedback_cache[cache_key] = {"adj": adj, "ts": now}
        # Evict oldest entries if cache too large
        if len(_feedback_cache) > _FEEDBACK_MAX_SIZE:
            oldest = sorted(_feedback_cache, key=lambda k: _feedback_cache[k]["ts"])
            for old_key in oldest[:len(_feedback_cache) - _FEEDBACK_MAX_SIZE]:
                del _feedback_cache[old_key]
    return adj


def _analyze_ats_record(lean_team, sport):
    """
    Checks real historical ATS record from tm_historical_games (preferred),
    falls back to tracker ledger.

    +4 if >60% ATS (min 15 decided games for real data)
    -3 if <40% ATS

    Returns:
        Dict with ats_bonus, ats_penalty, and detail.
    """
    result = {"ats_bonus": False, "ats_penalty": False, "detail": ""}

    if not lean_team:
        return result

    # Prefer real ATS from historical games DB
    record = None
    try:
        from test_model.db import get_real_team_ats
        record = get_real_team_ats(lean_team, sport)
    except Exception:
        pass

    # Fallback to tracker ledger
    if record is None:
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

    Uses the override registry to check for validated lean direction overrides.
    Falls back to universal defaults (public=favorite, vegas=underdog) when
    no validated override exists.

    Negative spread = home team favored.
    """
    if current_spread is None:
        return None

    lean_override = get_override(sport, "lean_direction", None)

    if lean_override == "always_underdog":
        # NBA + NHL: validated — always lean underdog in all slots
        return away_team if current_spread < 0 else home_team

    if lean_override == "flipped":
        # NFL-style: public=underdog, vegas=favorite
        if slot_type in ("public", "skip", "caution"):
            return away_team if current_spread < 0 else home_team
        elif slot_type in ("vegas", "trap"):
            return home_team if current_spread < 0 else away_team
        return away_team if current_spread < 0 else home_team

    # Default slot_dependent: public=favorite, vegas=underdog
    if slot_type in ("public", "caution"):
        return home_team if current_spread < 0 else away_team
    elif slot_type in ("vegas", "trap"):
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
                     vegas_trap_bonus=0,
                     line_toward_dog=False, line_toward_fav=False,
                     day_of_week=""):
    """
    Composite scoring using the override registry. Only validated overrides
    deviate from UNIVERSAL_DEFAULTS; weak/insufficient_data fall back to
    pre-tuning baselines.

    Returns:
        (total_score, breakdown_dict)
    """
    defaults = UNIVERSAL_DEFAULTS
    breakdown = {"slot": 0, "line_movement": 0, "line_direction": 0,
                 "trell": 0,
                 "rank_scam": 0, "spread_discrepancy": 0,
                 "trend_discrepancy": 0, "overunder": 0, "weather": 0,
                 "spread_penalty": 0, "day_penalty": 0,
                 "b2b": 0, "ats_record": 0, "home_away_split": 0,
                 "public_betting": 0, "feedback": 0, "head_to_head": 0,
                 "vegas_trap": 0}

    # Public slot bonus — validated overrides or universal default
    if slot_type == "public":
        breakdown["slot"] = get_override(sport, "public_slot_bonus",
                                         defaults["public_slot_bonus"])
    if line_confirms:
        breakdown["line_movement"] = score_line_movement(line_magnitude, sport=sport)
    if trell_applies:
        if sport == "nba":
            breakdown["trell"] = NBA_UNVALIDATED_CAPS["trell"]
        elif sport == "cbb":
            breakdown["trell"] = CBB_UNVALIDATED_CAPS["trell"]
        else:
            breakdown["trell"] = 5
    if rank_scam_applies:
        breakdown["rank_scam"] = 5
    if spread_disc_applies:
        breakdown["spread_discrepancy"] = 5
    if trend_disc_applies:
        breakdown["trend_discrepancy"] = 5
    if ou_disc_applies:
        # NFL: validated +5; unvalidated sports: informational +3; others: +5
        if sport in ("nba", "cbb"):
            breakdown["overunder"] = 3
        else:
            breakdown["overunder"] = 5
    if weather_applies:
        breakdown["weather"] = 5

    # B2B — override or universal default
    if b2b_bonus:
        breakdown["b2b"] = get_override(sport, "b2b_bonus", defaults["b2b_bonus"])
    elif b2b_penalty:
        breakdown["b2b"] = get_override(sport, "b2b_penalty", defaults["b2b_penalty"])

    # ATS — override or universal default
    if ats_bonus:
        breakdown["ats_record"] = get_override(sport, "ats_bonus", defaults["ats_bonus"])
    elif ats_penalty:
        breakdown["ats_record"] = get_override(sport, "ats_penalty", defaults["ats_penalty"])

    # Home/away split — override or universal default
    if home_away_applies:
        breakdown["home_away_split"] = get_override(sport, "home_away_split",
                                                     defaults["home_away_split"])

    if sport == "nba":
        breakdown["public_betting"] = min(public_betting_bonus, NBA_UNVALIDATED_CAPS["public_betting"])
    elif sport == "cbb":
        breakdown["public_betting"] = min(public_betting_bonus, CBB_UNVALIDATED_CAPS["public_betting"])
    else:
        breakdown["public_betting"] = public_betting_bonus
    breakdown["feedback"] = feedback_adjustment

    # H2H revenge / dominance — override or universal default
    if h2h_revenge_bonus:
        breakdown["head_to_head"] = get_override(sport, "h2h_revenge",
                                                  defaults["h2h_revenge"])
    elif h2h_dominance_bonus:
        breakdown["head_to_head"] = get_override(sport, "h2h_dominance",
                                                  defaults["h2h_dominance"])

    if sport == "nba":
        breakdown["vegas_trap"] = min(vegas_trap_bonus, NBA_UNVALIDATED_CAPS["vegas_trap"])
    elif sport == "cbb":
        breakdown["vegas_trap"] = min(vegas_trap_bonus, CBB_UNVALIDATED_CAPS["vegas_trap"])
    else:
        breakdown["vegas_trap"] = vegas_trap_bonus

    # Line direction — override or universal default (0)
    if line_toward_dog:
        breakdown["line_direction"] = get_override(sport, "line_toward_dog",
                                                    defaults["line_toward_dog"])
    elif line_toward_fav:
        breakdown["line_direction"] = get_override(sport, "line_toward_fav",
                                                    defaults["line_toward_fav"])

    # Day penalties — each sport/day combo checked via override registry
    day_lower = day_of_week.lower()
    # Map sport+day to override names
    _day_penalty_map = {
        ("nba", "tuesday"): "tuesday_penalty",
        ("cbb", "sunday"): "sunday_penalty",
        ("nhl", "friday"): "friday_penalty",
    }
    day_override_name = _day_penalty_map.get((sport, day_lower))
    if day_override_name:
        breakdown["day_penalty"] = get_override(sport, day_override_name, 0)

    # Spread adjustments — override registry for each bucket, fallback to generic rules
    if spread_value is not None:
        spread_abs = abs(spread_value)
        if sport == "nba":
            if 3 <= spread_abs < 5:
                breakdown["spread_penalty"] = get_override(sport, "spread_3_5_bonus", 0)
            elif 5 <= spread_abs < 7:
                breakdown["spread_penalty"] = get_override(sport, "spread_5_7_penalty", 0)
            elif spread_abs >= 13:
                breakdown["spread_penalty"] = get_override(sport, "spread_13_plus_penalty", 0)
        elif sport == "cbb":
            if 6 <= spread_abs < 10:
                breakdown["spread_penalty"] = get_override(sport, "spread_6_10_bonus", 0)
            elif spread_abs < 3:
                breakdown["spread_penalty"] = get_override(sport, "spread_0_3_penalty", 0)
            elif spread_abs >= 15:
                breakdown["spread_penalty"] = get_override(sport, "spread_15_plus_penalty", 0)
        elif sport == "nfl":
            if 3 <= spread_abs < 7:
                breakdown["spread_penalty"] = get_override(sport, "spread_3_7_bonus", 0)
            elif spread_abs < 3:
                breakdown["spread_penalty"] = get_override(sport, "spread_0_3_penalty", 0)
            elif spread_abs >= 10:
                breakdown["spread_penalty"] = get_override(sport, "spread_10_plus_penalty", 0)
        elif sport == "nhl" and spread_abs > 8:
            breakdown["spread_penalty"] = -3
        elif sport == "cfb" and spread_abs > 14:
            breakdown["spread_penalty"] = -3

    total = sum(breakdown.values())
    total = max(total, 0)
    return total, breakdown
