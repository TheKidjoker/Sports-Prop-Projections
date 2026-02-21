from datetime import datetime, timedelta
from api_client import get_todays_games, get_all_injuries, get_game_spread, get_player_season_averages
from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot
from trell_rule import is_star_player, is_recent_injury, evaluate_trell_rule


def scan_all_games():
    """
    Fetch all today's games, analyze each, return ranked list.

    Returns:
        List of analysis dicts sorted by confirmation_score descending.
    """
    games = get_todays_games()
    if not games:
        return []

    all_injuries = get_all_injuries()

    # Sort by game_date to determine first game
    sorted_games = sorted(games, key=lambda g: g.get("game_date", ""))

    now = datetime.now()
    day_of_week = now.strftime("%A")

    results = []
    for i, game in enumerate(sorted_games):
        is_first_game = (i == 0)
        analysis = _analyze_single_game(game, day_of_week, all_injuries, is_first_game)
        results.append(analysis)

    # Sort by confirmation_score descending
    results.sort(key=lambda r: r.get("confirmation_score", 0), reverse=True)
    return results


def _analyze_single_game(game, day_of_week, all_injuries, is_first_game):
    """
    Returns analysis dict for one game.
    """
    event_id = game["event_id"]
    home_team = game["home_team"]
    away_team = game["away_team"]
    game_date_str = game.get("game_date", "")

    # Parse game time — classify using PST, display using EST
    hour, minute = None, None
    game_time_est = ""
    if game_date_str:
        try:
            game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
            pst_dt = game_dt - timedelta(hours=8)
            hour, minute = pst_dt.hour, pst_dt.minute
            est_dt = game_dt - timedelta(hours=5)
            try:
                game_time_est = est_dt.strftime("%-I:%M %p")
            except ValueError:
                game_time_est = est_dt.strftime("%I:%M %p").lstrip("0")
        except (ValueError, TypeError):
            pass

    # Classify slot (with first-game override)
    if is_first_game:
        slot_type = first_game_slot_override(day_of_week)
    elif hour is not None:
        slot_type = classify_slot(day_of_week, hour, minute)
    else:
        slot_type = "unknown"

    # Line movement
    opening, current = get_game_spread(event_id)
    line_movement_data = {"available": False}
    line_confirms = False

    if opening is not None and current is not None:
        movement = detect_movement(opening, current)
        confirmed = confirms_slot(movement, slot_type)
        line_confirms = confirmed
        line_movement_data = {
            "available": True,
            "opening_spread": opening,
            "current_spread": current,
            "movement": movement,
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
                player_stats = get_player_season_averages(player_id)
                if player_stats:
                    star, star_reason = is_star_player(player_stats)

            injured_stars.append({
                "player_name": injury["player_name"],
                "is_star": star,
                "star_reason": star_reason,
                "is_recent": recent,
                "status": injury["status"],
            })

    trell_result = evaluate_trell_rule(injured_stars, slot_type)

    # Moneyline rule
    moneyline_recommend = False
    current_spread = current
    if opening is not None and current is not None:
        if abs(current) >= 3:
            moneyline_recommend = True

    # Calculate score and cover percentage
    score, _ = _calculate_score(slot_type, line_confirms, trell_result.get("applies", False))
    cover_pct = round(50 + (score / 20) * 45, 1)

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

    return {
        "home_team": home_team,
        "away_team": away_team,
        "event_id": event_id,
        "game_time_est": game_time_est,
        "cover_pct": cover_pct,
        "lean_team": lean_team,
        "action": action,
        "recommendation": recommendation,
    }


def _fmt_spread(val):
    """Format a spread value with +/- sign."""
    if val > 0:
        return "+" + str(val)
    return str(val)


def _determine_lean(slot_type, home_team, away_team, current_spread):
    """
    Determine which team to lean towards based on slot type and spread.

    Public slot → lean favorite (public money tends to be right).
    Vegas slot → lean underdog (sharp money fades the public).
    Negative spread = home team favored.
    """
    if current_spread is None:
        return None

    if slot_type == "public":
        # Lean with the favorite
        return home_team if current_spread < 0 else away_team
    elif slot_type == "vegas":
        # Lean with the underdog (against public)
        return away_team if current_spread < 0 else home_team

    return None


def _calculate_score(slot_type, line_confirms, trell_applies):
    """
    Scoring:
      +10  public slot
      +5   line movement confirms slot
      +5   trell rule confirms
      = 20 max

    Returns:
        (total_score, breakdown_dict)
    """
    breakdown = {"slot": 0, "line_movement": 0, "trell": 0}

    if slot_type == "public":
        breakdown["slot"] = 10
    if line_confirms:
        breakdown["line_movement"] = 5
    if trell_applies:
        breakdown["trell"] = 5

    total = sum(breakdown.values())
    return total, breakdown
