"""
Test Model Collector — iterates 2 years of in-season dates per sport,
fetches games, spreads, and final scores from ESPN, and stores in
tm_historical_games.  Runs as background thread with progress polling.
"""

import time
import threading
from datetime import datetime, timedelta

from api_client import get_todays_games, get_game_spread, get_game_final_score, get_game_overunder
from test_model import db as tm_db

# Season date ranges by sport (approximate)
SEASON_RANGES = {
    "nba": [
        ("20231024", "20240414"),
        ("20241022", "20250413"),
        ("20251022", "20260413"),
    ],
    "nhl": [
        ("20231010", "20240418"),
        ("20241008", "20250417"),
        ("20251008", "20260417"),
    ],
    "cfb": [
        ("20230826", "20231209"),
        ("20240824", "20241207"),
        ("20250823", "20251206"),
    ],
    "nfl": [
        ("20230907", "20240211"),
        ("20240905", "20250209"),
        ("20250904", "20260208"),
    ],
    "cbb": [
        ("20231106", "20240409"),
        ("20241104", "20250407"),
        ("20251103", "20260406"),
    ],
}

# Global progress dict for polling
_collection_progress = {}
_collection_lock = threading.Lock()


def get_collection_status(sport):
    with _collection_lock:
        return dict(_collection_progress.get(sport, {}))


def _generate_dates(start_str, end_str):
    start = datetime.strptime(start_str, "%Y%m%d")
    end = datetime.strptime(end_str, "%Y%m%d")
    current = start
    dates = []
    while current <= end:
        dates.append(current.strftime("%Y%m%d"))
        current += timedelta(days=1)
    return dates


def _compute_home_covered(home_score, away_score, spread):
    if home_score is None or away_score is None or spread is None:
        return None
    adjusted = home_score + spread
    if adjusted > away_score:
        return 1   # home covered
    elif adjusted < away_score:
        return 0   # home did not cover
    else:
        return -1  # push


def collect_sport(sport):
    """
    Collect all historical games for a sport.  Runs synchronously.
    Call via start_collection_thread() for background execution.
    """
    ranges = SEASON_RANGES.get(sport)
    if not ranges:
        return

    # Build full date list, skip already-done dates
    done_dates = tm_db.get_done_dates(sport)
    all_dates = []
    for start_str, end_str in ranges:
        all_dates.extend(_generate_dates(start_str, end_str))

    # Only process dates up through today (skip future dates)
    today_str = datetime.now().strftime("%Y%m%d")
    all_dates = [d for d in all_dates if d <= today_str]
    pending_dates = sorted([d for d in all_dates if d not in done_dates], reverse=True)
    total = len(all_dates)
    done_count = len(done_dates)

    with _collection_lock:
        _collection_progress[sport] = {
            "status": "running",
            "total_dates": total,
            "done_dates": done_count,
            "current_date": "",
            "games_collected": tm_db.count_historical_games(sport),
            "errors": 0,
        }

    for date_str in pending_dates:
        with _collection_lock:
            _collection_progress[sport]["current_date"] = date_str

        try:
            games = get_todays_games(sport, date_str=date_str)
            games_found = 0

            for game in games:
                event_id = game["event_id"]

                # Get spread data
                opening, closing = get_game_spread(event_id, sport)

                # Get final score
                home_score, away_score, is_final = get_game_final_score(event_id, sport)

                # Get over/under
                ou = get_game_overunder(event_id, sport)

                # Compute home_covered
                home_covered = _compute_home_covered(home_score, away_score, closing)

                tm_db.upsert_historical_game({
                    "event_id": event_id,
                    "sport": sport,
                    "game_date": game.get("game_date", date_str),
                    "home_team": game["home_team"],
                    "away_team": game["away_team"],
                    "home_team_id": game.get("home_team_id"),
                    "away_team_id": game.get("away_team_id"),
                    "home_rank": game.get("home_rank"),
                    "away_rank": game.get("away_rank"),
                    "closing_spread": closing,
                    "opening_spread": opening,
                    "over_under": ou,
                    "home_score": home_score,
                    "away_score": away_score,
                    "home_covered": home_covered,
                    "game_status": "STATUS_FINAL" if is_final else "STATUS_IN_PROGRESS",
                })
                games_found += 1

            tm_db.upsert_collection_progress(sport, date_str, "DONE", games_found)
            done_count += 1

            with _collection_lock:
                _collection_progress[sport]["done_dates"] = done_count
                _collection_progress[sport]["games_collected"] = (
                    _collection_progress[sport].get("games_collected", 0) + games_found
                )

        except Exception as e:
            tm_db.upsert_collection_progress(sport, date_str, "ERROR", 0, str(e))
            with _collection_lock:
                _collection_progress[sport]["errors"] = (
                    _collection_progress[sport].get("errors", 0) + 1
                )

        # Be polite to ESPN
        time.sleep(0.5)

    with _collection_lock:
        _collection_progress[sport]["status"] = "complete"
        _collection_progress[sport]["current_date"] = ""


def start_collection_thread(sport):
    """Start collection in a background thread.  Returns immediately."""
    with _collection_lock:
        existing = _collection_progress.get(sport, {})
        if existing.get("status") == "running":
            return False  # Already running

    t = threading.Thread(target=collect_sport, args=(sport,), daemon=True)
    t.start()
    return True
