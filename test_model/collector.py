"""
Test Model Collector — iterates 2 years of in-season dates per sport,
fetches games, spreads, and final scores from ESPN, and stores in
tm_historical_games.  Runs as background thread with progress polling.

After ESPN collection, optionally backfills missing spreads from The Odds API
(requires ODDS_API_KEY env var — graceful degradation when not set).
"""

import os
import time
import threading
import requests
from collections import defaultdict
from datetime import datetime, timedelta

from api_client import get_todays_games, get_game_spread, get_game_final_score, get_game_overunder
from test_model import db as tm_db

ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")

# The Odds API sport keys
ODDS_API_SPORT_KEYS = {
    "nba": "basketball_nba",
    "nhl": "icehockey_nhl",
    "nfl": "americanfootball_nfl",
    "cfb": "americanfootball_ncaaf",
    "cbb": "basketball_ncaab",
}

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

    # Run Odds API backfill for games missing spreads
    if ODDS_API_KEY:
        with _collection_lock:
            _collection_progress[sport]["current_date"] = "Backfilling spreads..."
        try:
            backfill_spreads_from_odds_api(sport)
        except Exception as e:
            print(f"[ODDS API] Backfill error: {e}", flush=True)

    with _collection_lock:
        _collection_progress[sport]["status"] = "complete"
        _collection_progress[sport]["current_date"] = ""
        _collection_progress[sport]["games_collected"] = tm_db.count_historical_games(sport)


def start_collection_thread(sport):
    """Start collection in a background thread.  Returns immediately."""
    with _collection_lock:
        existing = _collection_progress.get(sport, {})
        if existing.get("status") == "running":
            return False  # Already running

    t = threading.Thread(target=collect_sport, args=(sport,), daemon=True)
    t.start()
    return True


# ─── The Odds API Spread Backfill ──────────────────────────────────────────

def _normalize_team_name(name):
    """Normalize team name for fuzzy matching between ESPN and Odds API."""
    return name.strip().lower().replace(".", "").replace("'", "")


def _match_odds_to_game(odds_game, home_team, away_team):
    """Check if an Odds API game matches an ESPN game by team names."""
    oh = _normalize_team_name(odds_game.get("home_team", ""))
    oa = _normalize_team_name(odds_game.get("away_team", ""))
    eh = _normalize_team_name(home_team)
    ea = _normalize_team_name(away_team)
    # Match if either name is a substring of the other (handles "Los Angeles Lakers" vs "Lakers")
    return (oh in eh or eh in oh) and (oa in ea or ea in oa)


def fetch_odds_api_spreads(sport_key, date_iso):
    """
    Fetch historical spreads from The Odds API for a given date.

    Args:
        sport_key: Odds API sport key (e.g., "basketball_nba")
        date_iso: ISO 8601 date string (e.g., "2024-01-15T00:00:00Z")

    Returns:
        List of dicts: [{home_team, away_team, opening_spread, closing_spread}]
        Empty list on error or no data.
    """
    if not ODDS_API_KEY:
        return []

    url = f"https://api.the-odds-api.com/v4/historical/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "us",
        "markets": "spreads",
        "oddsFormat": "american",
        "date": date_iso,
    }

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 422:
            return []  # No data for this date
        resp.raise_for_status()

        # Track remaining credits from headers
        remaining = resp.headers.get("x-requests-remaining", "?")
        used = resp.headers.get("x-requests-used", "?")
        print(f"[ODDS API] Credits: {used} used, {remaining} remaining", flush=True)

        data = resp.json()
        games = data.get("data", [])
        results = []

        for game in games:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            bookmakers = game.get("bookmakers", [])

            # Find FanDuel or DraftKings as primary, fallback to first available
            closing_spread = None
            opening_spread = None
            for bk in bookmakers:
                bk_key = bk.get("key", "")
                markets = bk.get("markets", [])
                for market in markets:
                    if market.get("key") != "spreads":
                        continue
                    outcomes = market.get("outcomes", [])
                    for outcome in outcomes:
                        if _normalize_team_name(outcome.get("name", "")) in _normalize_team_name(home) or \
                           _normalize_team_name(home) in _normalize_team_name(outcome.get("name", "")):
                            spread_val = outcome.get("point")
                            if spread_val is not None:
                                if closing_spread is None or bk_key in ("fanduel", "draftkings"):
                                    closing_spread = float(spread_val)
                                if opening_spread is None:
                                    opening_spread = float(spread_val)

            if closing_spread is not None:
                results.append({
                    "home_team": home,
                    "away_team": away,
                    "opening_spread": opening_spread,
                    "closing_spread": closing_spread,
                })

        return results

    except Exception as e:
        print(f"[ODDS API] Error fetching {sport_key} for {date_iso}: {e}", flush=True)
        return []


def backfill_spreads_from_odds_api(sport):
    """
    Second pass: find games with NULL closing_spread and try to fill from The Odds API.
    Groups games by date and makes one API call per date.
    Rate limited to 1 request per second.
    """
    if not ODDS_API_KEY:
        print("[ODDS API] No ODDS_API_KEY set, skipping backfill.", flush=True)
        return 0

    sport_key = ODDS_API_SPORT_KEYS.get(sport)
    if not sport_key:
        return 0

    # Get all games without spreads
    games = tm_db.get_historical_games(sport)
    no_spread = [g for g in games if g.get("closing_spread") is None
                 and g.get("game_status") == "STATUS_FINAL"]

    if not no_spread:
        print(f"[ODDS API] No games without spreads for {sport}.", flush=True)
        return 0

    # Group by date
    by_date = defaultdict(list)
    for g in no_spread:
        date_key = g.get("game_date", "")[:10]  # "2024-01-15"
        if date_key:
            by_date[date_key].append(g)

    print(f"[ODDS API] Backfilling {len(no_spread)} games across {len(by_date)} dates for {sport}.", flush=True)

    updated = 0
    for date_str in sorted(by_date.keys()):
        date_games = by_date[date_str]
        # Format as ISO for API: "2024-01-15T12:00:00Z"
        date_iso = f"{date_str}T12:00:00Z"

        odds_data = fetch_odds_api_spreads(sport_key, date_iso)
        if not odds_data:
            time.sleep(1)
            continue

        for game in date_games:
            for odds_game in odds_data:
                if _match_odds_to_game(odds_game, game["home_team"], game["away_team"]):
                    closing = odds_game["closing_spread"]
                    opening = odds_game.get("opening_spread")
                    home_covered = _compute_home_covered(
                        game.get("home_score"), game.get("away_score"), closing
                    )
                    tm_db.upsert_historical_game({
                        **game,
                        "closing_spread": closing,
                        "opening_spread": opening or game.get("opening_spread"),
                        "home_covered": home_covered,
                    })
                    updated += 1
                    break

        time.sleep(1)  # Rate limit: 1 request per second

    print(f"[ODDS API] Backfilled {updated} games for {sport}.", flush=True)
    return updated
