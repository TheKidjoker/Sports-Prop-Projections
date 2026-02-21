from datetime import datetime, timezone, timedelta

STAR_THRESHOLDS = {
    "nba": {
        "min_ppg": 18,
        "min_mpg": 28,
        "alt": [
            {"min_ppg": 15, "min_apg": 5},
            {"min_ppg": 15, "min_rpg": 8},
        ],
    },
}

RECENCY_HOURS = 72
TRELL_BOOST = 5


def is_star_player(player_stats, sport="nba"):
    """
    Check if a player's stats meet star thresholds.

    Args:
        player_stats: Dict with keys like ppg, rpg, apg, mpg
        sport: Sport key (default "nba")

    Returns:
        (bool, reason_str)
    """
    if not player_stats:
        return False, ""

    thresholds = STAR_THRESHOLDS.get(sport)
    if not thresholds:
        return False, ""

    ppg = player_stats.get("ppg", 0)
    mpg = player_stats.get("mpg", 0)
    apg = player_stats.get("apg", 0)
    rpg = player_stats.get("rpg", 0)

    # Primary threshold: PPG + MPG
    if ppg >= thresholds["min_ppg"] and mpg >= thresholds["min_mpg"]:
        return True, f"PPG: {ppg}, MPG: {mpg}"

    # Alternative thresholds
    for alt in thresholds.get("alt", []):
        meets_all = True
        for key, min_val in alt.items():
            stat_key = key.replace("min_", "")
            if player_stats.get(stat_key, 0) < min_val:
                meets_all = False
                break
        if meets_all:
            reason_parts = [f"{k.replace('min_', '').upper()}: {player_stats.get(k.replace('min_', ''), 0)}"
                            for k in alt]
            return True, ", ".join(reason_parts)

    return False, ""


def is_recent_injury(injury_date_str):
    """
    True if injury reported within RECENCY_HOURS of now.

    Args:
        injury_date_str: ISO format date string

    Returns:
        bool
    """
    if not injury_date_str:
        return False

    try:
        injury_dt = datetime.fromisoformat(injury_date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - injury_dt) <= timedelta(hours=RECENCY_HOURS)
    except (ValueError, TypeError):
        return False


def evaluate_trell_rule(injured_stars, slot_type):
    """
    Main Trell Rule entry point.

    Only fires if:
    - At least one star is out
    - Star status is "Out"
    - Injury is recent (within RECENCY_HOURS)
    - slot_type is "vegas"

    Args:
        injured_stars: List of dicts, each with:
            {player_name, is_star, star_reason, is_recent, status}
        slot_type: "public", "vegas", or "unknown"

    Returns:
        Dict: {applies, boost, star_out, reason}
    """
    result = {
        "applies": False,
        "boost": 0,
        "star_out": None,
        "reason": "No qualifying star injury found.",
    }

    if slot_type != "vegas":
        result["reason"] = "Trell Rule only applies in vegas slots."
        return result

    for star in injured_stars:
        if (star.get("is_star")
                and star.get("status", "").lower() == "out"
                and star.get("is_recent")):
            result["applies"] = True
            result["boost"] = TRELL_BOOST
            result["star_out"] = star["player_name"]
            result["reason"] = star.get("star_reason", "Star player out")
            return result

    return result
