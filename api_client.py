import os
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from api_cache import _cached_request, _espn_url, SPORT_MAP, CACHE_TTL  # noqa: F401

# How many hours after kickoff before a game is considered stale
STALE_HOURS = 2


def is_game_stale(game_date_str):
    """
    Returns True if the game's scheduled start was 2+ hours ago (UTC comparison).
    """
    if not game_date_str:
        return False
    try:
        game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - game_dt >= timedelta(hours=STALE_HOURS)
    except (ValueError, TypeError):
        return False


def _espn_player_stats_url(sport, athlete_id):
    """Build ESPN player stats URL."""
    info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
    return (
        f"https://site.web.api.espn.com/apis/common/v3/sports/"
        f"{info['category']}/{info['league']}/athletes/{athlete_id}/stats"
    )


def get_todays_games(sport="nba", date_str=None):
    """
    Fetches today's games from the ESPN scoreboard API.

    Args:
        sport: "nba", "nhl", "cfb", or "nfl"
        date_str: Optional YYYYMMDD string to fetch a specific date's games.

    Returns:
        List of dicts: [{event_id, home_team, away_team, game_status, ...}, ...]
        Empty list on failure.
    """
    try:
        url = _espn_url(sport, "scoreboard")
        params = {}
        if date_str:
            params["dates"] = date_str
        else:
            # Always pass explicit ET date — ESPN's default scoreboard can lag
            # behind and show yesterday's completed games instead of today's
            now_et = datetime.now(timezone.utc) - timedelta(hours=5)
            params["dates"] = now_et.strftime("%Y%m%d")
        data = _cached_request(url, params=params, timeout=10)
        if data is None:
            return []
        games = []

        for event in data.get("events", []):
            event_id = event.get("id")
            competition = event.get("competitions", [{}])[0]
            competitors = competition.get("competitors", [])

            home_team = None
            away_team = None
            home_team_id = None
            away_team_id = None
            home_rank = None
            away_rank = None

            for team in competitors:
                team_info = team.get("team", {})
                name = team_info.get("displayName", "")
                tid = team_info.get("id")

                # Extract ranking (curatedRank.current); 99 or 0 = unranked
                rank_val = team.get("curatedRank", {}).get("current", 99)
                rank = rank_val if rank_val not in (0, 99) else None

                if team.get("homeAway") == "home":
                    home_team = name
                    home_team_id = tid
                    home_rank = rank
                else:
                    away_team = name
                    away_team_id = tid
                    away_rank = rank

            game_date = event.get("date", "")

            # Extract game status
            game_status = (
                competition.get("status", {})
                .get("type", {})
                .get("name", "STATUS_SCHEDULED")
            )

            # Extract venue data
            venue_obj = competition.get("venue", {})
            venue_name = venue_obj.get("fullName", "")
            venue_address = venue_obj.get("address", {})
            venue_city = venue_address.get("city", "")
            venue_state = venue_address.get("state", "")

            if event_id and home_team and away_team:
                game_entry = {
                    "event_id": event_id,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_team_id": home_team_id,
                    "away_team_id": away_team_id,
                    "game_date": game_date,
                    "game_status": game_status,
                    "venue_name": venue_name,
                    "venue_city": venue_city,
                    "venue_state": venue_state,
                    "home_rank": home_rank,
                    "away_rank": away_rank,
                }

                # Capture inline weather for NFL from scoreboard
                if sport == "nfl":
                    weather_obj = competition.get("weather", {})
                    if weather_obj:
                        game_entry["weather"] = {
                            "temperature": weather_obj.get("temperature"),
                            "condition": weather_obj.get("displayValue", ""),
                            "wind_speed": weather_obj.get("windSpeed"),
                            "precipitation": weather_obj.get("precipitation"),
                        }

                games.append(game_entry)

        return games

    except (requests.RequestException, KeyError, IndexError):
        return []


def get_game_spread(event_id, sport="nba"):
    """
    Fetches opening and current home team spreads for a given game.

    Args:
        event_id: ESPN event ID
        sport: "nba" or "nhl"

    Returns:
        (opening_spread, current_spread) as floats, or (None, None) on failure
    """
    try:
        url = _espn_url(sport, "summary")
        data = _cached_request(url, params={"event": event_id}, timeout=10)
        if data is None:
            return None, None

        pickcenter = data.get("pickcenter", [])

        if not pickcenter:
            return None, None

        point_spread = pickcenter[0].get("pointSpread", {})
        home_spread = point_spread.get("home", {})

        opening = home_spread.get("open", {}).get("line")
        current = home_spread.get("close", {}).get("line")

        if opening is not None and current is not None:
            return float(opening), float(current)

        return None, None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None, None


def find_game_by_team(team_name, sport="nba"):
    """
    Searches today's games for a team name match (case-insensitive substring).

    Args:
        team_name: Team name to search for (e.g., "Lakers", "Los Angeles Lakers")
        sport: "nba" or "nhl"

    Returns:
        event_id if found, None otherwise
    """
    games = get_todays_games(sport)
    search = team_name.strip().lower()

    for game in games:
        if (search in game["home_team"].lower()
                or search in game["away_team"].lower()):
            return game["event_id"]

    return None


def get_all_injuries(sport="nba"):
    """
    Fetches current injuries from ESPN.

    Args:
        sport: "nba" or "nhl"

    Returns:
        Dict mapping team display name -> list of injury dicts.
    """
    try:
        url = _espn_url(sport, "injuries")
        data = _cached_request(url, timeout=10)
        if data is None:
            return {}

        injuries_by_team = {}

        for team_entry in data.get("injuries", []):
            team_name = team_entry.get("team", {}).get("displayName", "Unknown")
            team_injuries = []

            for item in team_entry.get("injuries", []):
                athlete = item.get("athlete", {})
                player_name = athlete.get("displayName", "")
                player_id = athlete.get("id")
                status = item.get("status", "")
                injury_date = item.get("date", "")
                short_comment = item.get("shortComment", "")

                if player_name:
                    team_injuries.append({
                        "player_name": player_name,
                        "player_id": player_id,
                        "status": status,
                        "injury_date": injury_date,
                        "short_comment": short_comment,
                    })

            if team_injuries:
                injuries_by_team[team_name] = team_injuries

        return injuries_by_team

    except (requests.RequestException, KeyError, IndexError):
        return {}


def get_player_season_averages(athlete_id, sport="nba"):
    """
    Fetches a player's season averages from ESPN.
    Checks Supabase DB cache first, falls back to ESPN API.

    Handles two API response formats:
    - Legacy: categories[].stats[] = [{name, value}, ...]
    - Current: categories[].names[] + statistics[].stats[] (positional arrays)

    Args:
        athlete_id: ESPN athlete ID
        sport: "nba", "nhl", "nfl", "cbb"

    Returns:
        Dict with stat keys or None on failure.
        NBA/CBB: {ppg, rpg, apg, mpg}
        NHL: {ptspg, gpg, apg, toi}
        NFL: {pass_ypg, qbr, rush_ypg, rec_ypg, total_td}
    """
    # Check Supabase cache first (24-hour TTL for season stats)
    import cache_manager
    supabase = cache_manager._get_supabase()
    if supabase:
        try:
            from datetime import datetime, timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            season = "2024-25"  # Current season - update annually
            result = (
                supabase.table("player_season_stats")
                .select("*")
                .eq("player_id", str(athlete_id))
                .eq("sport", sport)
                .eq("season", season)
                .gte("last_updated", cutoff.isoformat())
                .limit(1)
                .execute()
            )
            if result.data:
                row = result.data[0]
                # Map DB columns back to expected format
                cached = {}
                if sport in ("nba", "cbb"):
                    cached = {k: row[k] for k in ["ppg", "rpg", "apg", "mpg"] if row.get(k) is not None}
                elif sport == "nhl":
                    # Map DB columns to NHL keys
                    if row.get("points"):
                        cached["ptspg"] = row["points"]
                    if row.get("goals"):
                        cached["gpg"] = row["goals"]
                    if row.get("assists"):
                        cached["apg"] = row["assists"]
                elif sport == "nfl":
                    cached = {k: row[k] for k in ["pass_ypg", "qbr", "rush_ypg", "rec_ypg", "total_td"] if row.get(k) is not None}
                if cached:
                    return cached
        except Exception as e:
            # Silently fall through to ESPN API on DB errors
            pass

    # Fallback to ESPN API
    try:
        url = _espn_player_stats_url(sport, athlete_id)
        data = _cached_request(url, timeout=10)
        if data is None:
            return None

        categories = data.get("categories", [])
        stats = {}

        # Try the positional-array format first (current ESPN API)
        for category in categories:
            cat_name = category.get("name", "")
            names = category.get("names", [])
            statistics = category.get("statistics", [])

            if names and statistics:
                # Find the most recent season (last entry)
                latest = statistics[-1] if statistics else None
                if latest:
                    vals = latest.get("stats", [])
                    # Build name->value map
                    for i, stat_name in enumerate(names):
                        if i < len(vals):
                            try:
                                val = float(vals[i]) if vals[i] and "-" not in str(vals[i]) else None
                            except (ValueError, TypeError):
                                val = None
                            if val is not None:
                                stats[stat_name] = val

        # If positional format yielded results, map to our keys
        if stats:
            return _map_espn_stat_names(stats, sport)

        # Fallback: legacy dict format — categories[].stats[] = [{name, value}]
        stats = {}
        for category in categories:
            for stat in category.get("stats", []):
                if not isinstance(stat, dict):
                    continue
                name = stat.get("name", "")
                value = stat.get("value")
                if value is not None:
                    stats[name] = float(value)

        if stats:
            result = _map_espn_stat_names(stats, sport)
            # Cache in Supabase for future requests
            if result and supabase:
                try:
                    from datetime import datetime, timezone
                    season = "2024-25"
                    # Prepare row data
                    row_data = {
                        "player_id": str(athlete_id),
                        "sport": sport,
                        "season": season,
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                    # Add sport-specific stats
                    if sport in ("nba", "cbb"):
                        row_data.update({k: result[k] for k in ["ppg", "rpg", "apg", "mpg"] if k in result})
                    elif sport == "nhl":
                        if "ptspg" in result:
                            row_data["points"] = result["ptspg"]
                        if "gpg" in result:
                            row_data["goals"] = result["gpg"]
                        if "apg" in result:
                            row_data["assists"] = result["apg"]
                    elif sport == "nfl":
                        row_data.update({k: result[k] for k in ["pass_ypg", "qbr", "rush_ypg", "rec_ypg", "total_td"] if k in result})

                    # Upsert (insert or update)
                    supabase.table("player_season_stats").upsert(row_data).execute()
                except Exception:
                    pass  # Don't fail on cache write errors
            return result

        return None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def _map_espn_stat_names(raw_stats, sport):
    """Map ESPN stat names to our internal keys."""
    result = {}

    if sport == "nfl":
        mappings = {
            "passingYardsPerGame": "pass_ypg",
            "QBRating": "qbr", "QBR": "qbr",
            "rushingYardsPerGame": "rush_ypg",
            "receivingYardsPerGame": "rec_ypg",
            "totalTouchdowns": "total_td",
        }
        for espn_name, our_key in mappings.items():
            if espn_name in raw_stats:
                result[our_key] = raw_stats[espn_name]
        if result.get("pass_ypg") is not None or result.get("rush_ypg") is not None:
            return result
    elif sport == "nhl":
        mappings = {
            "avgPoints": "ptspg",
            "avgGoals": "gpg",
            "avgAssists": "apg",
            "avgTimeOnIce": "toi",
        }
        for espn_name, our_key in mappings.items():
            if espn_name in raw_stats:
                result[our_key] = raw_stats[espn_name]
        if result.get("ptspg") is not None:
            return result
    else:
        # NBA, CBB
        mappings = {
            "avgPoints": "ppg",
            "avgRebounds": "rpg",
            "avgAssists": "apg",
            "avgMinutes": "mpg",
        }
        for espn_name, our_key in mappings.items():
            if espn_name in raw_stats:
                result[our_key] = raw_stats[espn_name]
        if result.get("ppg") is not None:
            return result

    return None


def get_game_overunder(event_id, sport="nfl"):
    """
    Fetches the over/under total from ESPN pickcenter.

    Returns:
        Float total or None on failure.
    """
    try:
        url = _espn_url(sport, "summary")
        data = _cached_request(url, params={"event": event_id}, timeout=10)
        if data is None:
            return None

        pickcenter = data.get("pickcenter", [])
        if not pickcenter:
            return None

        return float(pickcenter[0].get("overUnder", 0)) or None

    except (KeyError, IndexError, ValueError, TypeError):
        return None


def get_team_recent_results(team_id, count=4, sport="nfl"):
    """
    Fetches last N game results for a team from ESPN.

    Returns:
        List of dicts: [{result: 'W'/'L', score: int, opp_score: int}, ...]
        or empty list on failure.
    """
    try:
        info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/"
            f"{info['category']}/{info['league']}/teams/{team_id}/schedule"
        )
        data = _cached_request(url, timeout=10)
        if data is None:
            return []

        events = data.get("events", [])

        results = []
        for event in reversed(events):
            competitions = event.get("competitions", [{}])
            if not competitions:
                continue
            comp = competitions[0]
            status_type = comp.get("status", {}).get("type", {}).get("name", "")
            if status_type != "STATUS_FINAL":
                continue

            competitors = comp.get("competitors", [])
            team_score = None
            opp_score = None
            for c in competitors:
                if str(c.get("id")) == str(team_id):
                    team_score = int(c.get("score", 0))
                else:
                    opp_score = int(c.get("score", 0))

            if team_score is not None and opp_score is not None:
                results.append({
                    "result": "W" if team_score > opp_score else "L",
                    "score": team_score,
                    "opp_score": opp_score,
                })
                if len(results) >= count:
                    break

        return results

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return []


def get_game_final_score(event_id, sport="nba"):
    """
    Fetches final score from ESPN game summary.

    Returns:
        (home_score, away_score, is_final) tuple.
        (None, None, False) on failure or if game not final.
    """
    try:
        url = _espn_url(sport, "summary")
        data = _cached_request(url, params={"event": event_id}, timeout=10)
        if data is None:
            return None, None, False

        header = data.get("header", {})
        competitions = header.get("competitions", [])
        if not competitions:
            return None, None, False

        comp = competitions[0]
        status_name = comp.get("status", {}).get("type", {}).get("name", "")
        is_final = status_name == "STATUS_FINAL"

        if not is_final:
            return None, None, False

        competitors = comp.get("competitors", [])
        home_score = None
        away_score = None
        for c in competitors:
            if c.get("homeAway") == "home":
                home_score = int(c.get("score", 0))
            else:
                away_score = int(c.get("score", 0))

        if home_score is not None and away_score is not None:
            return home_score, away_score, True

        return None, None, False

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None, None, False


def get_game_boxscore_players(event_id, sport="nba"):
    """
    Fetch per-player box score data from ESPN game summary.

    Returns:
        {
            home_team: str, away_team: str,
            home_players: [{name, minutes, points, ...}],
            away_players: [{name, minutes, points, ...}],
        }
        or None on failure.
    """
    try:
        url = _espn_url(sport, "summary")
        data = _cached_request(url, params={"event": event_id}, timeout=10)
        if data is None:
            return None

        boxscore = data.get("boxscore", {})
        teams_data = boxscore.get("players", [])
        if not teams_data or len(teams_data) < 2:
            return None

        # Get team names from header
        header = data.get("header", {})
        competitions = header.get("competitions", [])
        home_team = away_team = ""
        if competitions:
            for c in competitions[0].get("competitors", []):
                tn = c.get("team", {}).get("displayName", "")
                if c.get("homeAway") == "home":
                    home_team = tn
                else:
                    away_team = tn

        result = {"home_team": home_team, "away_team": away_team,
                  "home_players": [], "away_players": []}

        for team_entry in teams_data:
            team_name = team_entry.get("team", {}).get("displayName", "")
            is_home = (team_name == home_team)
            key = "home_players" if is_home else "away_players"

            stats_sets = team_entry.get("statistics", [])
            if not stats_sets:
                continue

            stat_set = stats_sets[0]
            labels = [l.lower() for l in stat_set.get("labels", [])]
            athletes = stat_set.get("athletes", [])

            for athlete in athletes:
                player_info = athlete.get("athlete", {})
                name = player_info.get("displayName", "")
                stats = athlete.get("stats", [])

                if not name or not stats:
                    continue

                player = {"name": name}

                # Map stats by label
                for idx, label in enumerate(labels):
                    if idx < len(stats):
                        val = stats[idx]
                        # Parse time-based stats (MIN, TOI)
                        if label in ("min", "toi") and isinstance(val, str) and ":" in val:
                            try:
                                parts = val.split(":")
                                player[label] = int(parts[0]) + int(parts[1]) / 60
                            except (ValueError, IndexError):
                                player[label] = 0
                        else:
                            try:
                                player[label] = float(val)
                            except (ValueError, TypeError):
                                player[label] = val

                result[key].append(player)

        return result

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_player_game_log_espn(player_name, athlete_id, team_id, sport, count=7):
    """
    Fetches recent game stats for a player via ESPN team schedule + boxscore data.
    Works for any ESPN-supported sport (CBB, CFB, NHL, etc.).

    Args:
        player_name: Player display name for matching in boxscores
        athlete_id: ESPN athlete ID (not used for matching, reserved for future)
        team_id: ESPN team ID to fetch schedule from
        sport: Sport key ("cbb", "nhl", etc.)
        count: Number of recent games to fetch (default 7)

    Returns:
        List of dicts: [{pts, reb, ast, min, date}, ...] or None
    """
    if not team_id:
        return None

    try:
        events = get_team_schedule(team_id, sport)
        if not events:
            return None

        # Filter to completed games, sort by date descending
        completed = []
        for event in reversed(events):
            comps = event.get("competitions", [{}])
            if not comps:
                continue
            status = comps[0].get("status", {}).get("type", {}).get("name", "")
            if status == "STATUS_FINAL":
                completed.append(event)
            if len(completed) >= count:
                break

        if not completed:
            return None

        name_lower = player_name.lower()
        game_log = []

        for event in completed:
            event_id = event.get("id")
            event_date = event.get("date", "")
            if not event_id:
                continue

            box = get_game_boxscore_players(event_id, sport)
            if not box:
                continue

            # Search both home and away players for this player
            found = None
            for side in ("home_players", "away_players"):
                for p in box.get(side, []):
                    if p.get("name", "").lower() == name_lower:
                        found = p
                        break
                if found:
                    break

            if not found:
                continue

            entry = {
                "pts": found.get("pts", 0),
                "reb": found.get("reb", 0),
                "ast": found.get("ast", 0) or found.get("a", 0),
                "min": found.get("min", 0) or found.get("toi", 0),
                "date": event_date[:10] if event_date else "",
            }
            if sport == "nhl":
                entry["g"] = found.get("g", 0)
                entry["sog"] = found.get("sog", 0)
            game_log.append(entry)

        return game_log if game_log else None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_team_schedule(team_id, sport="nba"):
    """
    Fetches a team's schedule from ESPN.
    Cached via _cached_request so repeated calls for B2B + H2H reuse the same data.

    Returns:
        List of event dicts from the schedule, or empty list on failure.
    """
    try:
        info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/"
            f"{info['category']}/{info['league']}/teams/{team_id}/schedule"
        )
        data = _cached_request(url, timeout=10)
        if data is None:
            return []
        return data.get("events", [])
    except (requests.RequestException, KeyError, IndexError):
        return []


def check_back_to_back(team_id, game_date_str, sport="nba"):
    """
    Checks if a team played the day before the given game date.

    Args:
        team_id: ESPN team ID
        game_date_str: ISO date string of the game to check
        sport: "nba" or "nhl"

    Returns:
        True if the team played yesterday (back-to-back), False otherwise.
    """
    if not game_date_str:
        return False

    try:
        game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
        yesterday = (game_dt - timedelta(days=1)).strftime("%Y-%m-%d")

        events = get_team_schedule(team_id, sport)
        for event in events:
            event_date = event.get("date", "")
            if not event_date:
                continue
            try:
                evt_dt = datetime.fromisoformat(event_date.replace("Z", "+00:00"))
                evt_day = evt_dt.strftime("%Y-%m-%d")
                if evt_day == yesterday:
                    # Verify the game was actually played (final)
                    comps = event.get("competitions", [{}])
                    if comps:
                        status = comps[0].get("status", {}).get("type", {}).get("name", "")
                        if status == "STATUS_FINAL":
                            return True
            except (ValueError, TypeError):
                continue

        return False
    except (ValueError, TypeError):
        return False


def get_previous_matchup(team_id, opponent_name, sport="nba"):
    """
    Finds the most recent completed matchup between a team and an opponent this season.
    Reuses get_team_schedule (same cached response as B2B check).

    Args:
        team_id: ESPN team ID of one of the teams
        opponent_name: Display name of the opponent
        sport: Sport key

    Returns:
        Dict with {margin, team_won} or None if no prior matchup found.
        margin is positive = team_id's team won by that many.
    """
    try:
        events = get_team_schedule(team_id, sport)
        opp_lower = opponent_name.lower()

        for event in reversed(events):
            comps = event.get("competitions", [{}])
            if not comps:
                continue
            comp = comps[0]

            # Only look at completed games
            status = comp.get("status", {}).get("type", {}).get("name", "")
            if status != "STATUS_FINAL":
                continue

            competitors = comp.get("competitors", [])
            team_score = None
            opp_score = None
            is_opponent = False

            for c in competitors:
                c_name = c.get("team", {}).get("displayName", "")
                c_score = int(c.get("score", 0))
                if str(c.get("id")) == str(team_id):
                    team_score = c_score
                elif opp_lower in c_name.lower():
                    opp_score = c_score
                    is_opponent = True

            if is_opponent and team_score is not None and opp_score is not None:
                margin = team_score - opp_score
                return {
                    "margin": margin,
                    "team_won": margin > 0,
                    "team_score": team_score,
                    "opp_score": opp_score,
                }

        return None
    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_team_roster_leaders(team_id, sport="nba", limit=3):
    """
    Fetches top players by PPG from ESPN team endpoint + individual player stats.
    Gets the roster, then fetches season averages for each player to find leaders.

    Returns:
        List of dicts: [{athlete_id, name, ppg, rpg, apg, mpg}, ...]
        or empty list on failure.
    """
    try:
        info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/"
            f"{info['category']}/{info['league']}/teams/{team_id}"
        )
        data = _cached_request(url, params={"enable": "roster"}, timeout=10)
        if data is None:
            return []

        team_data = data.get("team", data)
        athletes = team_data.get("athletes", [])

        if not athletes:
            return []

        # Filter out injured-OUT players, collect IDs for stat lookup
        candidates = []
        for athlete in athletes:
            a_id = athlete.get("id")
            name = athlete.get("displayName") or athlete.get("fullName", "")
            if not a_id or not name:
                continue

            injuries = athlete.get("injuries", [])
            if injuries:
                status = injuries[0].get("status", "")
                if status.lower() == "out":
                    continue

            candidates.append({"athlete_id": a_id, "name": name})

        # Fetch season averages for each candidate in parallel
        # Limit to first 5 to speed up on-demand props loading
        top_candidates = candidates[:5]
        leaders = []
        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = {
                pool.submit(get_player_season_averages, cand["athlete_id"], sport): cand
                for cand in top_candidates
            }
            for future in futures:
                cand = futures[future]
                stats = future.result()
                if sport == "nhl":
                    if stats and stats.get("ptspg", 0) > 0:
                        leaders.append({
                            "athlete_id": cand["athlete_id"],
                            "name": cand["name"],
                            "ppg": stats.get("ptspg", 0),   # Map ptspg → ppg for PRISM compat
                            "gpg": stats.get("gpg", 0),      # Goals per game
                            "rpg": 0,                         # No rebounds in hockey
                            "apg": stats.get("apg", 0),
                            "mpg": stats.get("toi", 0),       # Time on ice → minutes
                        })
                else:
                    if stats and stats.get("ppg", 0) > 0:
                        leaders.append({
                            "athlete_id": cand["athlete_id"],
                            "name": cand["name"],
                            "ppg": stats.get("ppg", 0),
                            "rpg": stats.get("rpg", 0),
                            "apg": stats.get("apg", 0),
                            "mpg": stats.get("mpg", 0),
                        })

        leaders.sort(key=lambda x: x["ppg"], reverse=True)
        return leaders[:limit]

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return []


def get_team_defensive_stats(team_id, sport="nba"):
    """
    Fetches points allowed per game from ESPN team record (avgPointsAgainst).

    Returns:
        dict {"pts_allowed_per_game": float} or None
    """
    try:
        info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/"
            f"{info['category']}/{info['league']}/teams/{team_id}"
        )
        data = _cached_request(url, timeout=10)
        if data is None:
            return None

        team_data = data.get("team", data)
        record = team_data.get("record", {})
        items = record.get("items", [])

        for item in items:
            if item.get("type") == "total":
                for stat in item.get("stats", []):
                    if isinstance(stat, dict):
                        name = stat.get("name", "")
                        if name == "avgPointsAgainst":
                            return {"pts_allowed_per_game": float(stat.get("value", 0))}
                    elif isinstance(stat, str) and stat == "avgPointsAgainst":
                        # Some responses use flat key-value in stats list
                        continue

                # Also check if avgPointsAgainst is a direct stat key
                stats_dict = {s.get("name"): s.get("value") for s in item.get("stats", [])
                              if isinstance(s, dict)}
                if "avgPointsAgainst" in stats_dict:
                    return {"pts_allowed_per_game": float(stats_dict["avgPointsAgainst"])}

        return None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


def get_team_stats(team_id, sport="nba"):
    """
    Fetch comprehensive team stats from ESPN /statistics endpoint.
    Returns a flat dict of stat_name -> float_value, or None on failure.

    Merges two data sources:
      1. /teams/{id}/statistics — general, offensive, defensive categories
      2. /teams/{id} record — avgPointsAgainst, avgPointsFor (team record)
    """
    try:
        info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
        base = (
            f"https://site.api.espn.com/apis/site/v2/sports/"
            f"{info['category']}/{info['league']}/teams/{team_id}"
        )

        # Fetch statistics endpoint
        stats_url = base + "/statistics"
        stats_data = _cached_request(stats_url, timeout=10)

        result = {}

        if stats_data:
            # ESPN structure: results.stats.categories[].stats[]
            categories = []
            results_obj = stats_data.get("results", {})
            if isinstance(results_obj, dict):
                stats_obj = results_obj.get("stats", {})
                if isinstance(stats_obj, dict):
                    categories = stats_obj.get("categories", [])
                elif isinstance(stats_obj, list):
                    categories = stats_obj
            elif isinstance(results_obj, list):
                categories = results_obj

            # Also check top-level categories fallback
            if not categories:
                categories = stats_data.get("categories", [])

            for category in categories:
                if not isinstance(category, dict):
                    continue
                stat_list = category.get("stats", [])
                for stat in stat_list:
                    if isinstance(stat, dict):
                        name = stat.get("name") or stat.get("abbreviation", "")
                        value = stat.get("value")
                        if name and value is not None:
                            try:
                                result[name] = float(value)
                            except (ValueError, TypeError):
                                pass

        # Merge team record stats (avgPointsAgainst, avgPointsFor)
        record_data = _cached_request(base, timeout=10)
        if record_data:
            team_data = record_data.get("team", record_data)
            record = team_data.get("record", {})
            items = record.get("items", [])
            for item in items:
                if item.get("type") == "total":
                    for stat in item.get("stats", []):
                        if isinstance(stat, dict):
                            name = stat.get("name", "")
                            value = stat.get("value")
                            if name and value is not None and name not in result:
                                try:
                                    result[name] = float(value)
                                except (ValueError, TypeError):
                                    pass

        return result if result else None

    except (requests.RequestException, KeyError, IndexError, ValueError, TypeError):
        return None


_league_avg_cache = {}
_league_avg_ts = {}


def get_league_avg_stats(sport="nba"):
    """
    Fetch league-wide average stats by querying all teams' statistics.
    Cached in-memory for 24 hours. Returns dict of stat averages or None.
    """
    import time
    now = time.time()
    if sport in _league_avg_cache and now - _league_avg_ts.get(sport, 0) < 86400:
        return _league_avg_cache[sport]

    try:
        info = SPORT_MAP.get(sport, SPORT_MAP["nba"])
        url = (
            f"https://site.api.espn.com/apis/site/v2/sports/"
            f"{info['category']}/{info['league']}/teams?limit=50"
        )
        data = _cached_request(url, timeout=15)
        if not data:
            return _league_avg_cache.get(sport)

        teams = (data.get("sports", [{}])[0]
                 .get("leagues", [{}])[0]
                 .get("teams", []))
        team_ids = [t.get("team", t).get("id") for t in teams if t.get("team", t).get("id")]

        # Fetch stats for all teams in parallel
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {tid: pool.submit(get_team_stats, tid, sport) for tid in team_ids}
            all_stats = {tid: f.result() for tid, f in futures.items()}

        # Average key stats across all teams
        if sport == "nhl":
            stat_keys = ["avgGoals", "avgGoalsAllowed", "avgShots", "avgShotsAllowed",
                         "avgAssists", "avgPoints", "avgPointsAgainst"]
        else:
            stat_keys = ["avgRebounds", "avgSteals", "avgAssists", "avgBlocks",
                         "avgPoints", "avgPointsAgainst", "avgTurnovers",
                         "avgFieldGoalsAttempted", "avgFreeThrowsAttempted",
                         "avgOffensiveRebounds"]
        averages = {}
        for key in stat_keys:
            vals = [s[key] for s in all_stats.values() if s and key in s]
            if vals:
                averages[key] = round(sum(vals) / len(vals), 2)

        if averages:
            _league_avg_cache[sport] = averages
            _league_avg_ts[sport] = now

        return averages if averages else None
    except Exception:
        return _league_avg_cache.get(sport)


# ─── Backward-compatible re-exports ──────────────────────────────────────────
# These functions were moved to api_players.py and api_odds.py but are
# re-exported here so existing imports (app.py, tracker.py, etc.) keep working.

from api_players import (  # noqa: E402, F401
    get_player_id,
    get_recent_game_points,
    get_player_recent_points,
    get_player_game_log,
)

from api_odds import (  # noqa: E402, F401
    ODDS_API_SPORT_MAP,
    get_odds_comparison,
    _match_odds_to_game,
    get_player_props_odds,
    get_game_weather_espn,
    get_game_weather_openweather,
)
