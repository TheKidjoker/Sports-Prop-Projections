def detect_movement(opening_spread, current_spread):
    """
    Determines if the spread moved with the public or against it (Vegas),
    and by how much.

    A more negative spread means the favorite is getting more points
    (public money pushing the line). A more positive spread means the
    line moved against the public (sharp/Vegas money).

    Args:
        opening_spread: Opening spread as string or float (e.g., "+4.5", "-6")
        current_spread: Current spread as string or float (e.g., "+1.5", "-7")

    Returns:
        (direction, magnitude) tuple:
            direction: "public", "vegas", or "none"
            magnitude: absolute points moved (float)
    """
    opening = _parse_spread(opening_spread)
    current = _parse_spread(current_spread)

    if opening is None or current is None:
        return "none", 0.0

    magnitude = abs(current - opening)

    if current < opening:
        return "public", magnitude
    elif current > opening:
        return "vegas", magnitude
    else:
        return "none", 0.0


def confirms_slot(movement_direction, slot_type):
    """
    Checks whether the line movement direction confirms the time slot type.

    Args:
        movement_direction: "public", "vegas", or "none"
        slot_type: "public", "vegas", or "unknown"

    Returns:
        True if movement confirms the slot type, False otherwise
    """
    if movement_direction == "public" and slot_type == "public":
        return True
    if movement_direction == "vegas" and slot_type == "vegas":
        return True
    return False


def score_line_movement(magnitude, sport="nba"):
    """
    Converts line movement magnitude to a graduated score.

    NBA (backtested — line movement has minimal lift):
      0-1 pts = 0, 1-2 pts = 2, 2-3 pts = 3, 3+ pts = 5

    Other sports (default):
      0-1 pts = 0, 1-2 pts = 3, 2-3 pts = 5, 3+ pts = 8

    Args:
        magnitude: absolute points the line moved
        sport: sport key for sport-specific scoring

    Returns:
        int score
    """
    if magnitude < 1:
        return 0
    if sport == "nba":
        if magnitude < 2:
            return 2
        if magnitude < 3:
            return 3
        return 5
    # All other sports — original weights
    if magnitude < 2:
        return 3
    if magnitude < 3:
        return 5
    return 8


def _parse_spread(value):
    """
    Parses a spread value from string or numeric to float.
    Handles formats like "+4.5", "-6", "4.5", -6.0, etc.

    Returns:
        Float value or None if parsing fails
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None
