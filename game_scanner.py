from datetime import datetime, timedelta
from api_client import get_todays_games, get_all_injuries, get_game_spread, get_player_season_averages
from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot
from trell_rule import is_star_player, is_recent_injury, evaluate_trell_rule


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
EXPECTED_SPREADS = {
    (1, 5): (24, 28),
    (6, 10): (18, 22),
    (11, 15): (14, 18),
    (16, 20): (10, 14),
    (21, 25): (7, 10),
}


def _get_expected_spread(rank):
    """Returns (low, high) expected spread for a rank tier, or None."""
    for (lo, hi), spread_range in EXPECTED_SPREADS.items():
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


def _detect_spread_discrepancy(home_rank, away_rank, current_spread, slot_type):
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

    expected = _get_expected_spread(rank)
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


def scan_all_games(sport="nba"):
    """
    Fetch all today's games, analyze each, return ranked list.

    Args:
        sport: "nba" or "nhl"

    Returns:
        List of analysis dicts sorted by confirmation_score descending.
    """
    games = get_todays_games(sport)
    if not games:
        return []

    all_injuries = get_all_injuries(sport)

    # Sort by game_date to determine first game / game index
    sorted_games = sorted(games, key=lambda g: g.get("game_date", ""))
    total_games = len(sorted_games)

    now = datetime.now()
    day_of_week = now.strftime("%A")

    results = []
    for i, game in enumerate(sorted_games):
        is_first_game = (i == 0)
        analysis = _analyze_single_game(
            game, day_of_week, all_injuries, is_first_game,
            sport=sport, total_games_on_slate=total_games, game_index=i,
        )
        results.append(analysis)

    # Sort by confirmation_score descending
    results.sort(key=lambda r: r.get("confirmation_score", 0), reverse=True)
    return results


def _analyze_single_game(game, day_of_week, all_injuries, is_first_game,
                          sport="nba", total_games_on_slate=1, game_index=0):
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
            if sport == "cfb":
                classify_dt = game_dt - timedelta(hours=5)  # EST (same as display)
            elif sport == "nhl":
                classify_dt = game_dt - timedelta(hours=6)  # CST
            else:
                classify_dt = game_dt - timedelta(hours=8)  # PST
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
    if sport == "cfb":
        if hour is not None:
            slot_type = classify_slot(day_of_week, hour, minute, sport="cfb")
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

    # Line movement
    opening, current = get_game_spread(event_id, sport)
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

    if sport == "cfb":
        rank_scam = _detect_rank_scam(home_rank, away_rank, current, slot_type)
        spread_discrepancy = _detect_spread_discrepancy(home_rank, away_rank, current, slot_type)

    # Moneyline rule
    moneyline_recommend = False
    current_spread = current
    if opening is not None and current is not None:
        if abs(current) >= 3:
            moneyline_recommend = True

    # Calculate score and cover percentage
    rank_scam_applies = rank_scam.get("is_rank_scam", False)
    spread_disc_applies = spread_discrepancy.get("is_discrepancy", False)
    score, _ = _calculate_score(
        slot_type, line_confirms, trell_result.get("applies", False),
        rank_scam_applies=rank_scam_applies, spread_disc_applies=spread_disc_applies,
    )
    max_score = 30 if sport == "cfb" else 20
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
        "cover_pct": cover_pct,
        "lean_team": lean_team,
        "action": action,
        "recommendation": recommendation,
    }

    # Include venue for NHL and CFB
    if sport in ("nhl", "cfb"):
        result["venue_name"] = game.get("venue_name", "")
        result["venue_city"] = game.get("venue_city", "")
        result["venue_state"] = game.get("venue_state", "")

    # Include rank data and slot info for CFB
    if sport == "cfb":
        result["home_rank"] = home_rank
        result["away_rank"] = away_rank
        result["slot_type"] = slot_type
        if rank_scam["is_rank_scam"]:
            result["rank_scam"] = rank_scam
        if spread_discrepancy["is_discrepancy"]:
            result["spread_discrepancy"] = spread_discrepancy

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
                     rank_scam_applies=False, spread_disc_applies=False):
    """
    Scoring:
      +10  public slot
      +5   line movement confirms slot
      +5   trell rule confirms
      +5   rank scam detected (CFB)
      +5   spread discrepancy detected (CFB)
      = 20 max (NBA/NHL), 30 max (CFB)

    Returns:
        (total_score, breakdown_dict)
    """
    breakdown = {"slot": 0, "line_movement": 0, "trell": 0,
                 "rank_scam": 0, "spread_discrepancy": 0}

    if slot_type == "public":
        breakdown["slot"] = 10
    if line_confirms:
        breakdown["line_movement"] = 5
    if trell_applies:
        breakdown["trell"] = 5
    if rank_scam_applies:
        breakdown["rank_scam"] = 5
    if spread_disc_applies:
        breakdown["spread_discrepancy"] = 5

    total = sum(breakdown.values())
    return total, breakdown
