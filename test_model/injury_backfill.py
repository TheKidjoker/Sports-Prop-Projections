"""
Injury Backfill — Retroactive star absence detection from ESPN box scores.

Instead of an external injuries API, detects star absences by comparing
expected star players (from rolling stat history) against actual box score
participants. Two-pass: first build player stat histories, then detect absences.
"""

import threading
import time
from collections import defaultdict

from test_model import db as tm_db
from trell_rule import is_star_player, STAR_THRESHOLDS

# ─── Progress Tracking ────────────────────────────────────────────────────
_backfill_progress = {}
_backfill_lock = threading.Lock()

WARMUP_GAMES = 30     # Games before we start detecting absences
MIN_GAMES_STAR = 3    # Player must appear in ≥3 of last 10 to be "expected"
LOOKBACK = 10         # Rolling window for player history
CACHE_CLEAR_INTERVAL = 25
API_DELAY = 0.5       # Seconds between API calls


def get_backfill_status(sport):
    with _backfill_lock:
        return dict(_backfill_progress.get(sport, {}))


def start_backfill_thread(sport):
    with _backfill_lock:
        existing = _backfill_progress.get(sport, {})
        if existing.get("status") == "running":
            return False
    t = threading.Thread(target=_run_backfill, args=(sport,), daemon=True)
    t.start()
    return True


# ─── Stat Key Mapping ─────────────────────────────────────────────────────
# Map ESPN box score labels → trell_rule stat keys for is_star_player()

def _map_box_stats_to_star_stats(player_box, sport):
    """Convert ESPN box score stats to trell_rule-compatible stat dict."""
    stats = {}
    if sport in ("nba", "cbb"):
        stats["ppg"] = player_box.get("pts", 0)
        stats["mpg"] = player_box.get("min", 0)
        stats["apg"] = player_box.get("ast", 0)
        stats["rpg"] = player_box.get("reb", 0)
    elif sport == "nhl":
        stats["ptspg"] = player_box.get("g", 0) + player_box.get("a", 0)
        stats["toi"] = player_box.get("toi", 0)
        stats["gpg"] = player_box.get("g", 0)
        stats["apg"] = player_box.get("a", 0)
    return stats


def _get_expected_stars(player_history, sport):
    """
    From a dict of {player_name: [stat_dicts]}, identify expected stars.
    A player is expected if they meet star thresholds on average stats
    over their most recent LOOKBACK games, with at least MIN_GAMES_STAR appearances.
    """
    if sport not in STAR_THRESHOLDS:
        return set()

    expected = set()
    for name, games in player_history.items():
        recent = games[-LOOKBACK:]
        if len(recent) < MIN_GAMES_STAR:
            continue

        # Average stats across recent games
        avg = {}
        for key in recent[0]:
            vals = [g.get(key, 0) for g in recent]
            avg[key] = sum(vals) / len(vals) if vals else 0

        is_star, _ = is_star_player(avg, sport)
        if is_star:
            expected.add(name)

    return expected


def _run_backfill(sport):
    """Main backfill loop. Runs synchronously in a background thread."""
    from api_client import get_game_boxscore_players
    from api_cache import clear_cache

    with _backfill_lock:
        _backfill_progress[sport] = {
            "status": "running",
            "processed": 0,
            "total_games": 0,
            "absences_found": 0,
            "errors": 0,
        }

    try:
        games = tm_db.get_historical_games(sport)
        final_games = [g for g in games if g.get("game_status") == "STATUS_FINAL"]
        final_games.sort(key=lambda g: g.get("game_date", ""))

        total = len(final_games)
        with _backfill_lock:
            _backfill_progress[sport]["total_games"] = total

        # Rolling player stat history per team: {team_name: {player_name: [stat_dicts]}}
        team_players = defaultdict(lambda: defaultdict(list))
        absences_found = 0
        errors = 0

        for idx, game in enumerate(final_games):
            event_id = game.get("event_id")
            game_date = game.get("game_date", "")
            home_team = game.get("home_team", "")
            away_team = game.get("away_team", "")

            # Update progress
            with _backfill_lock:
                _backfill_progress[sport]["processed"] = idx + 1

            # Fetch box score
            try:
                box = get_game_boxscore_players(event_id, sport)
            except Exception:
                errors += 1
                with _backfill_lock:
                    _backfill_progress[sport]["errors"] = errors
                time.sleep(API_DELAY)
                continue

            if not box:
                errors += 1
                with _backfill_lock:
                    _backfill_progress[sport]["errors"] = errors
                time.sleep(API_DELAY)
                continue

            # Record participation for each team
            for team_name, players_key in [
                (home_team, "home_players"),
                (away_team, "away_players"),
            ]:
                participants = set()
                for p in box.get(players_key, []):
                    name = p.get("name", "")
                    if not name:
                        continue
                    participants.add(name)

                    # Build stat dict for history
                    star_stats = _map_box_stats_to_star_stats(p, sport)
                    team_players[team_name][name].append(star_stats)

                    # Keep history bounded
                    if len(team_players[team_name][name]) > LOOKBACK + 5:
                        team_players[team_name][name] = team_players[team_name][name][-LOOKBACK:]

                # After warmup, detect absences
                if idx >= WARMUP_GAMES:
                    expected_stars = _get_expected_stars(
                        team_players[team_name], sport
                    )
                    absent_stars = expected_stars - participants

                    for star_name in absent_stars:
                        tm_db.upsert_historical_injury(
                            sport=sport,
                            game_date=game_date,
                            team=team_name,
                            player_name=star_name,
                            status="Out",
                            event_id=event_id,
                            is_star=1,
                        )
                        absences_found += 1

                    with _backfill_lock:
                        _backfill_progress[sport]["absences_found"] = absences_found

            # Rate limiting
            time.sleep(API_DELAY)

            # Periodic cache clear
            if (idx + 1) % CACHE_CLEAR_INTERVAL == 0:
                clear_cache()

        with _backfill_lock:
            _backfill_progress[sport].update({
                "status": "complete",
                "processed": total,
                "absences_found": absences_found,
                "errors": errors,
            })

    except Exception as e:
        with _backfill_lock:
            _backfill_progress[sport].update({
                "status": "error",
                "message": str(e),
            })
