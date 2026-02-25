# ─── Shared Date Parsing ───────────────────────────────────────────────────────
# Single source for ISO date string parsing used across test_model modules.

from datetime import datetime, timedelta


def parse_iso_date(date_str):
    """
    Parse an ISO date string (with optional Z suffix) into a datetime.

    Returns:
        datetime or None on parse failure.
    """
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


def days_between(date_str1, date_str2, default=3):
    """
    Days between two ISO date strings.

    Returns:
        int days apart, or `default` if either can't be parsed.
    """
    d1 = parse_iso_date(date_str1)
    d2 = parse_iso_date(date_str2)
    if d1 is None or d2 is None:
        return default
    return abs((d2 - d1).days)


TZ_OFFSETS = {
    "cfb": 5,   # EST
    "cbb": 5,   # EST
    "nhl": 6,   # CST
    "nba": 8,   # PST
    "nfl": 8,   # PST
}


def parse_game_dt(game_date_str, sport):
    """
    Parse game_date ISO string to timezone-adjusted datetime for slot classification.

    Returns:
        datetime or None on failure.
    """
    dt = parse_iso_date(game_date_str)
    if dt is None:
        return None
    offset = TZ_OFFSETS.get(sport, 8)
    return dt - timedelta(hours=offset)
