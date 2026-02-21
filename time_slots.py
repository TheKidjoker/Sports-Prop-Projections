# ─── NBA SLOT RULES ───────────────────────────────────────────────────────────
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


# ─── NHL SLOT RULES ──────────────────────────────────────────────────────────
# NHL uses CST (UTC-6) for classification. Slate size determines behavior.
# 1 game  → vegas
# 2 games → 1st = public, 2nd = vegas
# 3+ games → time-based (CST):
NHL_TIME_SLOTS = [
    (19, 0, "vegas"),    # 7:00 PM CST
    (20, 0, "public"),   # 8:00 PM CST
    (20, 30, "vegas"),   # 8:30 PM CST
    (21, 0, "public"),   # 9:00 PM CST
    (21, 30, "vegas"),   # 9:30 PM CST
    (22, 0, "public"),   # 10:00 PM CST
]


# ─── CFB SLOT RULES ─────────────────────────────────────────────────────────
# CFB uses EST (UTC-5) directly — no timezone conversion needed for display.
# Day-of-week determines slot behavior:
#   Sunday 8pm = public
#   Monday night = trap (vegas)
#   Thursday/Friday = public
#   Saturday has time-specific slots

CFB_SATURDAY_SLOTS = [
    (12, 0, "public"),     # Sat 12:00 PM ET — public
    (15, 30, "vegas"),     # Sat 3:30 PM ET — vegas
    (16, 0, "public"),     # Sat 4:00 PM ET — public
    (19, 0, "vegas"),      # Sat 7:00 PM ET — vegas
    (19, 30, "public"),    # Sat 7:30 PM ET — public
    (20, 0, "vegas"),      # Sat 8:00 PM ET — vegas
    (22, 30, "vegas"),     # Sat 10:30 PM ET — vegas
]

# Day-level overrides (all times on that day get this slot type)
CFB_DAY_OVERRIDES = {
    "sunday": "public",     # 8pm Sunday games = public outcome
    "monday": "trap",       # Monday night = trap
    "thursday": "public",   # Thursday = public outcome
    "friday": "public",     # Friday = public outcome
}


def classify_cfb_slot(day_of_week, hour_est, minute_est):
    """
    Classifies a CFB game slot based on day of week and EST time.

    Args:
        day_of_week: Day name (e.g., 'saturday')
        hour_est: Game start hour in 24hr EST
        minute_est: Game start minute

    Returns:
        'public', 'vegas', 'scan', 'caution', 'trap', or 'unknown'
    """
    day = day_of_week.lower()

    # Day-level overrides
    if day in CFB_DAY_OVERRIDES:
        return CFB_DAY_OVERRIDES[day]

    # Saturday: time-based slots
    if day == "saturday":
        game_time = hour_est * 60 + minute_est
        best_match = None
        best_distance = float("inf")

        for slot_hour, slot_minute, slot_type in CFB_SATURDAY_SLOTS:
            slot_time = slot_hour * 60 + slot_minute
            distance = abs(game_time - slot_time)
            if distance < best_distance:
                best_distance = distance
                best_match = slot_type

        if best_distance <= 20:
            return best_match

    return "unknown"


def classify_nhl_slot(total_games, game_index, hour_cst, minute_cst):
    """
    Classifies an NHL game slot based on slate size and time.

    Args:
        total_games: Total number of NHL games on today's slate
        game_index: 0-based index of this game (sorted by start time)
        hour_cst: Game start hour in 24hr CST
        minute_cst: Game start minute

    Returns:
        'public', 'vegas', or 'unknown'
    """
    if total_games == 1:
        return "vegas"

    if total_games == 2:
        return "public" if game_index == 0 else "vegas"

    # 3+ games: time-based classification
    game_time = hour_cst * 60 + minute_cst
    best_match = None
    best_distance = float("inf")

    for slot_hour, slot_minute, slot_type in NHL_TIME_SLOTS:
        slot_time = slot_hour * 60 + slot_minute
        distance = abs(game_time - slot_time)
        if distance < best_distance:
            best_distance = distance
            best_match = slot_type

    if best_distance <= 20:
        return best_match

    return "unknown"


def classify_slot(day_of_week, hour, minute, sport="nba",
                  total_games_on_slate=None, game_index=None):
    """
    Classifies a game's time into 'public', 'vegas', or 'unknown'.

    For NBA: uses day-of-week + PST time.
    For NHL: dispatches to classify_nhl_slot (CST time, slate-based).

    Args:
        day_of_week: Day name (e.g., 'monday') — used for NBA only
        hour: Game start hour in 24hr (PST for NBA, CST for NHL)
        minute: Game start minute
        sport: "nba" or "nhl"
        total_games_on_slate: Total games today (NHL only)
        game_index: 0-based game index (NHL only)

    Returns:
        'public', 'vegas', or 'unknown'
    """
    if sport == "cfb":
        return classify_cfb_slot(day_of_week, hour, minute)

    if sport == "nhl":
        if total_games_on_slate is not None and game_index is not None:
            return classify_nhl_slot(total_games_on_slate, game_index, hour, minute)
        return "unknown"

    # NBA logic
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
    elif slot_type == "trap":
        return "TRAP GAME"
    elif slot_type == "scan":
        return "SCAN"
    elif slot_type == "caution":
        return "CAUTION"
    return "UNKNOWN"


# Day type mapping: public days vs vegas days (NBA only)
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
    Public day -> first game is 'vegas'. Vegas day -> first game is 'public'.
    """
    day_type = get_day_type(day_of_week)
    if day_type == "public":
        return "vegas"
    if day_type == "vegas":
        return "public"
    return "unknown"
