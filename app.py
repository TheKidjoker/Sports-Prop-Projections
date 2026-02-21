from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from projections import points_prediction, cover_rate
from api_client import (
    get_player_recent_points, get_todays_games, get_game_spread,
    get_all_injuries, get_player_season_averages,
)
from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot
from trell_rule import is_star_player, is_recent_injury, evaluate_trell_rule
from game_scanner import scan_all_games

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/games", methods=["GET"])
def api_games():
    """Returns today's games list for autocomplete."""
    try:
        games = get_todays_games()
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

            result.append({
                "home_team": game["home_team"],
                "away_team": game["away_team"],
                "game_time_est": game_time_est,
                "event_id": game["event_id"],
            })

        return jsonify({"games": result})

    except Exception as e:
        return jsonify({"games": [], "error": str(e)}), 500


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Scans all today's games, returns ranked results."""
    try:
        results = scan_all_games()
        return jsonify({"success": True, "games": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/predict", methods=["POST"])
def predict():
    try:
        data = request.get_json()

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
            todays_games = get_todays_games()
            search = team_name.lower()

            for game in todays_games:
                if search in game["home_team"].lower() or search in game["away_team"].lower():
                    matched_game = game
                    break

            if matched_game:
                home_team = matched_game["home_team"]
                away_team = matched_game["away_team"]
                game_date_str = matched_game.get("game_date", "")

                # Check if this is the first game of the day
                sorted_games = sorted(todays_games, key=lambda g: g.get("game_date", ""))
                is_first_game = (sorted_games and sorted_games[0].get("event_id") == matched_game["event_id"])

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

                # Line movement check
                opening, current = get_game_spread(matched_game["event_id"])

                if opening is not None and current is not None:
                    current_spread = current
                    movement = detect_movement(opening, current)
                    confirmed = confirms_slot(movement, slot_type)
                    line_confirmed = confirmed

                    # Moneyline rule
                    if abs(current) >= 3:
                        moneyline_recommend = True
                        moneyline_spread = current

                # Trell Rule evaluation
                all_injuries = get_all_injuries()
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
                            player_stats = get_player_season_averages(player_id)
                            if player_stats:
                                star, star_reason = is_star_player(player_stats)
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

        # Fetch player data (only if player name provided)
        recent_games = None
        player_avg = None
        prediction_data = None
        cover_rates_data = None

        if player_name:
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

        return jsonify({
            "success": True,
            "player_name": player_name or None,
            "recent_games": recent_games,
            "player_avg": player_avg,
            "lean_team": lean_team,
            "action": action,
            "prediction": prediction_data,
            "cover_rates": cover_rates_data,
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
