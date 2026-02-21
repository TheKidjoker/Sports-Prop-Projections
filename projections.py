def points_prediction(player_avg, vegas_line, slot_type=None, line_confirmed=False, trell_confirmed=False):
    """
    Determines whether to lean Over, Under, or Pass based on
    player average vs Vegas line.

    Args:
        player_avg: Player's average points
        vegas_line: Vegas points line
        slot_type: 'public', 'vegas', or None for no adjustment
        line_confirmed: True if line movement confirms the slot type
        trell_confirmed: True if Trell Rule applies (star player injury in vegas slot)

    Returns:
        (decision: str, confidence: float)
    """

    difference = player_avg - vegas_line
    probability = 0.5 + (difference / vegas_line)

    # Clamp probability between 0 and 1
    probability = max(0, min(probability, 1))

    confidence = round(probability * 100, 1)

    if probability >= 0.55:
        decision = "Over"
    elif probability <= 0.45:
        decision = "Under"
        confidence = round((1 - probability) * 100, 1)
    else:
        decision = "PASS"

    # Apply slot-based confidence adjustment
    if slot_type == "public":
        confidence = min(confidence + 10, 100)
    elif slot_type == "vegas":
        confidence = max(confidence - 10, 0)
        # Shift borderline picks toward PASS when Vegas has the edge
        if confidence < 55 and decision != "PASS":
            decision = "PASS"

    # Apply line movement confirmation boost
    if line_confirmed:
        confidence = min(confidence + 5, 100)

    # Apply Trell Rule boost
    if trell_confirmed:
        confidence = min(confidence + 5, 100)

    return decision, confidence


def cover_rate(game_points, vegas_line):
    """
    Calculates historical Over, Under, and Push rates
    for a given set of game results and a Vegas line.

    Returns:
        (over_rate: float, under_rate: float, push_rate: float)
    """

    over_hits = 0
    under_hits = 0
    push_hits = 0

    for points in game_points:
        if points > vegas_line:
            over_hits += 1
        elif points < vegas_line:
            under_hits += 1
        else:
            push_hits += 1

    total_games = len(game_points)

    if total_games == 0:
        return 0.0, 0.0, 0.0

    over_rate = round((over_hits / total_games) * 100, 1)
    under_rate = round((under_hits / total_games) * 100, 1)
    push_rate = round((push_hits / total_games) * 100, 1)

    return over_rate, under_rate, push_rate
