def detect_movement(opening_spread, current_spread):
    """
    Determines if the spread moved with the public or against it (Vegas).

    A more negative spread means the favorite is getting more points
    (public money pushing the line). A more positive spread means the
    line moved against the public (sharp/Vegas money).

    Args:
        opening_spread: Opening spread as string or float (e.g., "+4.5", "-6")
        current_spread: Current spread as string or float (e.g., "+1.5", "-7")

    Returns:
        "public" if line moved with the public (more negative),
        "vegas" if line moved against the public (more positive),
        "none" if no movement
    """
    opening = _parse_spread(opening_spread)
    current = _parse_spread(current_spread)

    if opening is None or current is None:
        return "none"

    if current < opening:
        return "public"
    elif current > opening:
        return "vegas"
    else:
        return "none"


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
