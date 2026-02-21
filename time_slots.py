# Public day slots — used for Monday, Wednesday, Friday (hour in 24hr PST, minute, slot_type)
PUBLIC_DAY_SLOTS = [
    (17, 0, "vegas"),    # 5:00 PM
    (18, 0, "public"),   # 6:00 PM
    (19, 0, "vegas"),    # 7:00 PM
    (19, 30, "public"),  # 7:30 PM
    (21, 0, "vegas"),    # 9:00 PM
    (22, 0, "public"),   # 10:00 PM
]

# Vegas day slots — used for Tuesday, Thursday, Saturday, Sunday (hour in 24hr PST, minute, slot_type)
VEGAS_DAY_SLOTS = [
    (16, 0, "public"),   # 4:00 PM
    (17, 0, "vegas"),    # 5:00 PM
    (18, 0, "public"),   # 6:00 PM
    (19, 0, "vegas"),    # 7:00 PM
    (19, 30, "public"),  # 7:30 PM
    (21, 0, "vegas"),    # 9:00 PM
    (22, 0, "public"),   # 10:00 PM
]

# Map each day to its slot schedule
DAY_SLOTS = {
    "monday":    PUBLIC_DAY_SLOTS,
    "tuesday":   VEGAS_DAY_SLOTS,
    "wednesday": PUBLIC_DAY_SLOTS,
    "thursday":  VEGAS_DAY_SLOTS,
    "friday":    PUBLIC_DAY_SLOTS,
    "saturday":  VEGAS_DAY_SLOTS,
    "sunday":    VEGAS_DAY_SLOTS,
}


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
    slots = DAY_SLOTS.get(day_of_week.lower())
    if slots is None:
        return "unknown"

    game_time = hour * 60 + minute
    best_match = None
    best_distance = float("inf")

    for slot_hour, slot_minute, slot_type in slots:
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


# Day type mapping: public days vs vegas days
PUBLIC_DAYS = {"monday", "wednesday", "friday"}
VEGAS_DAYS = {"tuesday", "thursday", "saturday", "sunday"}


def get_day_type(day_of_week):
    """
    Returns 'public' for Mon/Wed/Fri, 'vegas' for Tue/Thu/Sat/Sun.
    """
    day = day_of_week.lower()
    if day in PUBLIC_DAYS:
        return "public"
    if day in VEGAS_DAYS:
        return "vegas"
    return "unknown"


def first_game_slot_override(day_of_week):
    """
    First game of the day is opposite of day type.
    Public day → first game is 'vegas'. Vegas day → first game is 'public'.
    """
    day_type = get_day_type(day_of_week)
    if day_type == "public":
        return "vegas"
    if day_type == "vegas":
        return "public"
    return "unknown"
