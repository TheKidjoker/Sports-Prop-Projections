from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify
from projections import points_prediction, cover_rate
from api_client import (
    get_player_recent_points, get_todays_games, get_game_spread,
    get_all_injuries, get_player_season_averages, is_game_stale,
)
from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot
from trell_rule import is_star_player, is_recent_injury, evaluate_trell_rule
from game_scanner import scan_all_games
import tracker

app = Flask(__name__)
tracker.init_db()


def _get_games_with_transition(sport):
    """
    Fetch today's active games AND tomorrow's games combined.
    Tags each game with a date_label ("Today" or "Tomorrow").

    Returns:
        (games_list, slate_info) where slate_info = {game_count, has_today, has_tomorrow}
    """
    now_utc = datetime.now(timezone.utc)
    tomorrow_str = (now_utc + timedelta(days=1)).strftime("%Y%m%d")

    # Fetch today's + tomorrow's scoreboards in parallel
    with ThreadPoolExecutor(max_workers=2) as pool:
        today_future = pool.submit(get_todays_games, sport)
        tomorrow_future = pool.submit(get_todays_games, sport, tomorrow_str)
        today_games = today_future.result()
        tomorrow_games = tomorrow_future.result()

    # Filter out stale/final from today
    active_today = [
        g for g in today_games
        if not is_game_stale(g.get("game_date", ""))
        and g.get("game_status") != "STATUS_FINAL"
    ]
    for g in active_today:
        g["date_label"] = "Today"

    for g in tomorrow_games:
        g["date_label"] = "Tomorrow"

    combined = active_today + tomorrow_games

    slate = {
        "game_count": len(combined),
        "has_today": len(active_today) > 0,
        "has_tomorrow": len(tomorrow_games) > 0,
    }
    return combined, slate


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/games", methods=["GET"])
def api_games():
    """Returns today's games list for autocomplete."""
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"

        games, slate = _get_games_with_transition(sport)
        result = []
        for game in games:
            game_time_est = ""
            game_date_str = game.get("game_date", "")
            if game_date_str:
                try:
                    game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                    est_dt = game_dt - timedelta(hours=5)
                    try:
                        game_time_est = est_dt.strftime("%-I:%M %p")
                    except ValueError:
                        game_time_est = est_dt.strftime("%I:%M %p").lstrip("0")
                except (ValueError, TypeError):
                    pass

            entry = {
                "home_team": game["home_team"],
                "away_team": game["away_team"],
                "game_time_est": game_time_est,
                "event_id": game["event_id"],
                "date_label": game.get("date_label", ""),
            }

            if sport in ("nhl", "cfb", "cbb", "nfl"):
                entry["venue_name"] = game.get("venue_name", "")
                entry["venue_city"] = game.get("venue_city", "")
                entry["venue_state"] = game.get("venue_state", "")

            if sport in ("cfb", "cbb"):
                entry["home_rank"] = game.get("home_rank")
                entry["away_rank"] = game.get("away_rank")

            result.append(entry)

        return jsonify({"games": result, "slate": slate})

    except Exception as e:
        return jsonify({"games": [], "slate": {"showing_tomorrow": False, "game_count": 0}, "error": str(e)}), 500


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scans all today's games, returns ranked results."""
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()

        if sport == "all":
            sports = ("nba", "nhl", "cfb", "nfl", "cbb")
            all_results = {}
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(scan_all_games, s): s for s in sports}
                for future in futures:
                    s = futures[future]
                    all_results[s] = future.result()
                    try:
                        tracker.save_predictions(all_results[s], s)
                    except Exception:
                        pass
            return jsonify({"success": True, "all_sports": all_results})

        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"

        results = scan_all_games(sport)
        try:
            tracker.save_predictions(results, sport)
        except Exception:
            pass
        return jsonify({"success": True, "games": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json()
        sport = data.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"

        # Validate required fields
        player_name = data.get("player_name", "").strip()
        vegas_line = data.get("vegas_line")
        games = data.get("games")
        team_name = data.get("team_name", "").strip()

        if not player_name and not team_name:
            return jsonify({"success": False, "error": "Enter a player name, team name, or both."}), 400
        if vegas_line is None:
            return jsonify({"success": False, "error": "Vegas line is required."}), 400
        if games is None:
            return jsonify({"success": False, "error": "Number of recent games is required."}), 400

        try:
            vegas_line = float(vegas_line)
            games = int(games)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Vegas line and games must be valid numbers."}), 400

        # Auto-detect day of week
        day_of_week = datetime.now().strftime("%A")

        # Look up team game from ESPN (gets event_id + game time)
        slot_type = "unknown"
        line_confirmed = False
        trell_confirmed = False
        moneyline_recommend = False
        moneyline_spread = None
        lean_team = None
        current_spread = None
        matched_game = None

        if team_name:
            todays_games = get_todays_games(sport)
            search = team_name.lower()

            for game in todays_games:
                if search in game["home_team"].lower() or search in game["away_team"].lower():
                    matched_game = game
                    break

            if matched_game:
                # Block predictions on stale/finished games
                game_date_str = matched_game.get("game_date", "")
                game_status = matched_game.get("game_status", "")
                if is_game_stale(game_date_str) or game_status == "STATUS_FINAL":
                    return jsonify({
                        "success": False,
                        "error": "This game has already started or ended.",
                    }), 400

                home_team = matched_game["home_team"]
                away_team = matched_game["away_team"]

                # Sort to determine game index / first game
                sorted_games = sorted(todays_games, key=lambda g: g.get("game_date", ""))
                total_games = len(sorted_games)
                game_idx = 0
                for idx, g in enumerate(sorted_games):
                    if g.get("event_id") == matched_game["event_id"]:
                        game_idx = idx
                        break
                is_first_game = (game_idx == 0)

                if sport == "nfl":
                    # NFL: classify using PST (UTC-8)
                    if game_date_str:
                        try:
                            game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                            pst_dt = game_dt - timedelta(hours=8)
                            hour, minute = pst_dt.hour, pst_dt.minute

                            # Detect last non-SNF Sunday game
                            is_last_sunday = False
                            if day_of_week.lower() == "sunday":
                                snf_mins = 17 * 60 + 20
                                for g in reversed(sorted_games):
                                    gd = g.get("game_date", "")
                                    if gd:
                                        try:
                                            gdt = datetime.fromisoformat(gd.replace("Z", "+00:00"))
                                            gpst = gdt - timedelta(hours=8)
                                            gmins = gpst.hour * 60 + gpst.minute
                                            if abs(gmins - snf_mins) > 30:
                                                if g.get("event_id") == matched_game["event_id"]:
                                                    is_last_sunday = True
                                                break
                                        except (ValueError, TypeError):
                                            continue

                            slot_type = classify_slot(
                                day_of_week, hour, minute,
                                sport="nfl",
                                is_last_sunday_game=is_last_sunday,
                            )
                        except (ValueError, TypeError):
                            pass
                elif sport in ("cfb", "cbb"):
                    # CFB/CBB: classify using EST (UTC-5)
                    if game_date_str:
                        try:
                            game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                            est_dt = game_dt - timedelta(hours=5)
                            hour, minute = est_dt.hour, est_dt.minute
                            slot_type = classify_slot(day_of_week, hour, minute, sport=sport)
                        except (ValueError, TypeError):
                            pass
                elif sport == "nhl":
                    # NHL: classify using CST (UTC-6)
                    if game_date_str:
                        try:
                            game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                            cst_dt = game_dt - timedelta(hours=6)
                            hour, minute = cst_dt.hour, cst_dt.minute
                            slot_type = classify_slot(
                                day_of_week, hour, minute,
                                sport="nhl",
                                total_games_on_slate=total_games,
                                game_index=game_idx,
                            )
                        except (ValueError, TypeError):
                            pass
                else:
                    # NBA: first-game override or PST classification
                    if is_first_game:
                        slot_type = first_game_slot_override(day_of_week)
                    elif game_date_str:
                        try:
                            game_dt = datetime.fromisoformat(game_date_str.replace("Z", "+00:00"))
                            pst_dt = game_dt - timedelta(hours=8)
                            hour, minute = pst_dt.hour, pst_dt.minute
                            slot_type = classify_slot(day_of_week, hour, minute)
                        except (ValueError, TypeError):
                            pass

                # NFL skip slot: early return
                if sport == "nfl" and slot_type == "skip":
                    return jsonify({
                        "success": True,
                        "skip": True,
                        "player_name": player_name or None,
                        "home_team": home_team,
                        "away_team": away_team,
                        "slot_type": "skip",
                        "message": "Sunday Night Football — SKIP (do not bet this game).",
                    })

                # Line movement check
                opening, current = get_game_spread(matched_game["event_id"], sport)

                if opening is not None and current is not None:
                    current_spread = current
                    movement, magnitude = detect_movement(opening, current)
                    confirmed = confirms_slot(movement, slot_type)
                    line_confirmed = confirmed

                    # Sport-specific moneyline thresholds
                    ml_threshold = {"nba": 6, "nfl": 3, "cfb": 7, "cbb": 7}.get(sport)
                    if ml_threshold and abs(current) >= ml_threshold:
                        moneyline_recommend = True
                        moneyline_spread = current

                # Trell Rule evaluation
                all_injuries = get_all_injuries(sport)
                injured_stars = []

                for t_name in [home_team, away_team]:
                    team_injuries = all_injuries.get(t_name, [])
                    for injury in team_injuries:
                        if injury.get("status", "").lower() != "out":
                            continue
                        recent = is_recent_injury(injury.get("injury_date", ""))
                        player_id = injury.get("player_id")
                        star = False
                        star_reason = ""
                        if player_id:
                            player_stats = get_player_season_averages(player_id, sport)
                            if player_stats:
                                star, star_reason = is_star_player(player_stats, sport)
                        injured_stars.append({
                            "player_name": injury["player_name"],
                            "is_star": star,
                            "star_reason": star_reason,
                            "is_recent": recent,
                            "status": injury["status"],
                        })

                trell_result = evaluate_trell_rule(injured_stars, slot_type)
                trell_confirmed = trell_result.get("applies", False)

                # Determine lean team
                if current_spread is not None:
                    if slot_type == "public":
                        lean_team = home_team if current_spread < 0 else away_team
                    elif slot_type == "vegas":
                        lean_team = away_team if current_spread < 0 else home_team

        # Fetch player data (only if player name provided and NBA)
        recent_games = None
        player_avg = None
        prediction_data = None
        cover_rates_data = None

        if player_name and sport not in ("nhl", "cfb", "cbb", "nfl"):
            recent_games = get_player_recent_points(player_name, games)

            if not recent_games or len(recent_games) == 0:
                return jsonify({
                    "success": False,
                    "error": f"No recent game data available for '{player_name}'.",
                }), 404

            player_avg = round(sum(recent_games) / len(recent_games), 1)
            decision, confidence = points_prediction(
                player_avg, vegas_line, slot_type, line_confirmed, trell_confirmed
            )
            over_rate, under_rate, push_rate = cover_rate(recent_games, vegas_line)

            prediction_data = {"decision": decision, "confidence": confidence}
            cover_rates_data = {"over": over_rate, "under": under_rate, "push": push_rate}

        # Build clear action string with spread numbers
        action = None
        if lean_team and current_spread is not None:
            if moneyline_recommend:
                action = "Take " + lean_team + " Moneyline"
            else:
                if lean_team == matched_game["home_team"]:
                    lean_spread = current_spread
                else:
                    lean_spread = -current_spread
                limit = lean_spread - 1.5
                fs = lambda v: ("+" + str(v)) if v > 0 else str(v)
                action = ("Take " + lean_team + " " + fs(lean_spread) +
                          " or better — don't take past " + fs(limit))

        response_data = {
            "success": True,
            "player_name": player_name or None,
            "recent_games": recent_games,
            "player_avg": player_avg,
            "lean_team": lean_team,
            "action": action,
            "prediction": prediction_data,
            "cover_rates": cover_rates_data,
        }

        # Include venue for NHL, CFB, CBB, and NFL
        if sport in ("nhl", "cfb", "cbb", "nfl") and matched_game:
            response_data["venue_name"] = matched_game.get("venue_name", "")
            response_data["venue_city"] = matched_game.get("venue_city", "")
            response_data["venue_state"] = matched_game.get("venue_state", "")

        return jsonify(response_data)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    """Returns aggregated prediction tracking stats."""
    try:
        sport = request.args.get("sport", "").lower() or None
        if sport and sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = None
        stats = tracker.get_dashboard_stats(sport)
        return jsonify({"success": True, **stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/grade", methods=["POST"])
def api_grade():
    """Grades pending predictions by fetching final scores."""
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "").lower() or None
        if sport and sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = None
        result = tracker.grade_predictions(sport)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = "PORT" not in os.environ
    app.run(host="0.0.0.0", port=port, debug=debug)
