"""
Data Quality Report — completeness stats for historical game data.
"""

from test_model import db as tm_db


def nba_data_quality_report():
    """
    Return completeness stats for NBA historical data:
    total_games, games_with_spread, games_with_opening, games_with_ou,
    games_with_venue, games_per_season, date_coverage_pct, games_with_pinnacle.
    """
    return _data_quality_report("nba")


def _data_quality_report(sport):
    """Generic data quality report for any sport."""
    games = tm_db.get_historical_games(sport)
    total = len(games)

    if total == 0:
        return {
            "sport": sport,
            "total_games": 0,
            "games_with_spread": 0,
            "games_with_opening": 0,
            "games_with_ou": 0,
            "games_with_venue": 0,
            "games_with_pinnacle": 0,
            "games_final": 0,
            "games_per_season": {},
            "date_range": None,
        }

    with_spread = sum(1 for g in games if g.get("closing_spread") is not None)
    with_opening = sum(1 for g in games if g.get("opening_spread") is not None)
    with_ou = sum(1 for g in games if g.get("over_under") is not None)
    with_venue = sum(1 for g in games if g.get("venue_name"))
    with_pinnacle = sum(1 for g in games if g.get("pinnacle_spread") is not None)
    games_final = sum(1 for g in games if g.get("game_status") == "STATUS_FINAL")

    # Group by season (approximate: use year from game_date)
    by_season = {}
    for g in games:
        gd = g.get("game_date", "")[:7]  # "YYYY-MM"
        if len(gd) >= 7:
            month = int(gd[5:7])
            year = int(gd[:4])
            # NBA season spans Oct-Apr: Oct 2024 = 2024-25 season
            season = f"{year}-{str(year + 1)[-2:]}" if month >= 10 else f"{year - 1}-{str(year)[-2:]}"
            by_season[season] = by_season.get(season, 0) + 1

    dates = sorted(g.get("game_date", "") for g in games if g.get("game_date"))
    date_range = {"earliest": dates[0], "latest": dates[-1]} if dates else None

    return {
        "sport": sport,
        "total_games": total,
        "games_with_spread": with_spread,
        "games_with_opening": with_opening,
        "games_with_ou": with_ou,
        "games_with_venue": with_venue,
        "games_with_pinnacle": with_pinnacle,
        "games_final": games_final,
        "games_per_season": by_season,
        "date_range": date_range,
        "completeness": {
            "spread_pct": round(with_spread / total * 100, 1) if total > 0 else 0,
            "opening_pct": round(with_opening / total * 100, 1) if total > 0 else 0,
            "ou_pct": round(with_ou / total * 100, 1) if total > 0 else 0,
            "venue_pct": round(with_venue / total * 100, 1) if total > 0 else 0,
            "pinnacle_pct": round(with_pinnacle / total * 100, 1) if total > 0 else 0,
        },
    }
