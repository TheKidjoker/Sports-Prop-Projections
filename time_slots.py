# Monday time slot schedule (hour in 24hr PST, minute, slot_type)
MONDAY_SLOTS = [
    (17, 0, "vegas"),    # 5:00 PM
    (18, 0, "public"),   # 6:00 PM
    (19, 0, "vegas"),    # 7:00 PM
    (19, 30, "public"),  # 7:30 PM
    (21, 0, "vegas"),    # 9:00 PM
    (22, 0, "public"),   # 10:00 PM
]


def classify_slot(day_of_week, hour, minute):
    """
    Classifies a game's day + time into 'public', 'vegas', or 'unknown'.

    Args:
        day_of_week: Day name (e.g., 'monday')
        hour: Game start hour in 24hr PST
        minute: Game start minute

    Returns:
        'public', 'vegas', or 'unknown'
    """
    if day_of_week.lower() != "monday":
        return "unknown"

    game_time = hour * 60 + minute
    best_match = None
    best_distance = float("inf")

    for slot_hour, slot_minute, slot_type in MONDAY_SLOTS:
        slot_time = slot_hour * 60 + slot_minute
        distance = abs(game_time - slot_time)
        if distance < best_distance:
            best_distance = distance
            best_match = slot_type

    # Only match if within 20 minutes of a known slot
    if best_distance <= 20:
        return best_match

    return "unknown"


def get_slot_label(slot_type):
    """
    Returns a display label for the slot type.
    """
    if slot_type == "public":
        return "PUBLIC DAY"
    elif slot_type == "vegas":
        return "VEGAS SLOT"
    return "UNKNOWN"
