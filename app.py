import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, jsonify
import jwt
from projections import points_prediction, cover_rate
from api_client import (
    get_player_recent_points, get_todays_games, get_game_spread,
    get_all_injuries, get_player_season_averages, is_game_stale,
)
from time_slots import classify_slot, first_game_slot_override
from line_movement import detect_movement, confirms_slot
from trell_rule import is_star_player, is_recent_injury, evaluate_trell_rule
from constants import ML_THRESHOLDS, DATA_CONFIDENCE_LEVELS, wilson_interval
from game_scanner import (
    scan_all_games, get_game_props, get_top_props,
    classify_game_slot, _build_action_string,
)
import tracker
import scan_cache

try:
    from test_model import db as tm_db
    from test_model.collector import start_collection_thread, get_collection_status
    from test_model.features import compute_all_features
    from test_model.backtest import start_backtest_thread, get_backtest_status
    from test_model.scanner import scan_today_with_model
    from test_model.rules_backtest import start_rules_backtest_thread, get_rules_backtest_status
    from test_model.walkforward import start_walkforward_thread, get_walkforward_status
    from calibration import load_calibration, is_loaded, get_calibration_type
    HAS_TEST_MODEL = True
except Exception as _tm_err:
    import traceback
    print("[test_model] Import failed:", traceback.format_exc())
    HAS_TEST_MODEL = False

app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
tracker.init_db()
if HAS_TEST_MODEL:
    tm_db.init_tm_db()
    # Load calibration models from latest backtest runs
    for _cal_sport in ("nba", "nhl", "nfl", "cfb", "cbb"):
        try:
            _cal_run = tm_db.get_latest_model_run(_cal_sport, "rules_backtest")
            if _cal_run and _cal_run.get("model_params"):
                _cal_data = _cal_run["model_params"].get("calibration")
                if _cal_data:
                    load_calibration(_cal_sport, _cal_data)
                    if is_loaded(_cal_sport):
                        print(f"[calibration] Loaded {get_calibration_type(_cal_sport)} model for {_cal_sport}", flush=True)
        except Exception:
            pass
scan_cache.init()

# ─── Supabase Auth ──────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}

_jwks_client = None


def _get_jwks_client():
    """Lazily initialize JWKS client to avoid startup crash if Supabase is unreachable."""
    global _jwks_client
    if _jwks_client is None and SUPABASE_URL:
        try:
            _jwks_client = jwt.PyJWKClient(f"{SUPABASE_URL}/auth/v1/jwks")
        except Exception:
            pass
    return _jwks_client


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        jwks = _get_jwks_client()
        if not SUPABASE_JWT_SECRET and not jwks:
            # Auth not configured — allow through (local dev)
            request.user_email = "dev@local"
            return f(*args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid token"}), 401
        token = auth_header[7:]
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg", "HS256")
            payload = None

            if alg == "HS256" and SUPABASE_JWT_SECRET:
                # Standard HS256 verification
                payload = jwt.decode(
                    token, SUPABASE_JWT_SECRET,
                    algorithms=["HS256"],
                    audience="authenticated",
                )
            elif alg == "ES256" and jwks:
                # ES256 via JWKS
                try:
                    signing_key = jwks.get_signing_key_from_jwt(token)
                    payload = jwt.decode(
                        token, signing_key.key,
                        algorithms=["ES256"],
                        audience="authenticated",
                    )
                except Exception as jwks_err:
                    if isinstance(jwks_err, (jwt.ExpiredSignatureError, jwt.InvalidTokenError)):
                        raise
                    # JWKS unavailable — verify claims without signature
                    print(f"[AUTH] JWKS unavailable ({jwks_err}), verifying claims only", flush=True)
                    payload = jwt.decode(
                        token, options={"verify_signature": False},
                        algorithms=["ES256"],
                        audience="authenticated",
                    )
            elif alg == "ES256" and SUPABASE_JWT_SECRET:
                # ES256 token but no JWKS — verify claims without signature
                payload = jwt.decode(
                    token, options={"verify_signature": False},
                    algorithms=["ES256"],
                    audience="authenticated",
                )
            else:
                return jsonify({"error": "Unsupported token algorithm"}), 401
            request.user_email = (payload or {}).get("email", "")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError as e:
            print(f"[AUTH] JWT error: {type(e).__name__}: {e}", flush=True)
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


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


@app.route("/auth/<path:subpath>")
def auth_redirect(subpath):
    """Handle Supabase email confirmation/callback redirects."""
    return render_template("index.html")


@app.route("/api/auth/config", methods=["GET"])
def auth_config():
    return jsonify({
        "supabase_url": SUPABASE_URL,
        "supabase_anon_key": SUPABASE_ANON_KEY,
    })


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def auth_me():
    return jsonify({
        "email": getattr(request, "user_email", ""),
        "is_admin": _is_admin(),
    })


@app.route("/api/games", methods=["GET"])
@require_auth
def api_games():
    """Returns today's games list for autocomplete."""
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"

        # Signal visitor arrival — wake background cache refresh
        scan_cache.request_refresh(sport)

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
@require_auth
def api_scan():
    """Scans all today's games, returns ranked results.
    Returns cached results instantly when available, queues background refresh.
    """
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()

        if sport == "all":
            sports = ("nba", "nhl", "cfb", "nfl", "cbb")
            all_results = {}
            missing = []
            for s in sports:
                cached, age = scan_cache.get(s)
                if cached is not None:
                    all_results[s] = cached
                else:
                    missing.append(s)

            if not missing:
                # All cached — return instantly, queue refresh
                scan_cache.request_refresh(*sports)
                return jsonify({"success": True, "all_sports": all_results, "cached": True})

            # Scan missing sports (blocking)
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(scan_all_games, s): s for s in missing}
                for future in futures:
                    s = futures[future]
                    result = future.result()
                    all_results[s] = result
                    scan_cache.put(s, result)
                    try:
                        tracker.save_predictions(result, s)
                    except Exception:
                        pass
            return jsonify({"success": True, "all_sports": all_results})

        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"

        # Check cache first
        cached, age = scan_cache.get(sport)
        if cached is not None:
            scan_cache.request_refresh(sport)
            return jsonify({
                "success": True, "games": cached,
                "cached": True, "cache_age": round(age),
            })

        # No cache — blocking scan
        results = scan_all_games(sport)
        scan_cache.put(sport, results)
        try:
            tracker.save_predictions(results, sport)
        except Exception:
            pass
        return jsonify({"success": True, "games": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/props", methods=["GET"])
@require_auth
def api_props():
    """On-demand PRISM player props for a single game."""
    try:
        event_id = request.args.get("event_id", "")
        sport = request.args.get("sport", "nba").lower()
        if not event_id:
            return jsonify({"success": False, "error": "event_id required"}), 400
        if sport not in ("nba",):
            return jsonify({"success": True, "props": []})
        props = get_game_props(event_id, sport)
        return jsonify({"success": True, "props": props})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/top-props", methods=["GET"])
@require_auth
def api_top_props():
    """Generate PRISM player props for ALL today's games at once."""
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba",):
            return jsonify({"success": True, "props": []})
        props = get_top_props(sport)
        return jsonify({"success": True, "props": props})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/predict", methods=["POST"])
@require_auth
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

                # Detect last non-SNF Sunday game for NFL
                is_last_sunday = False
                if sport == "nfl" and day_of_week.lower() == "sunday":
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

                slot_type, _, _, _, _ = classify_game_slot(
                    game_date_str, day_of_week, sport,
                    is_first_game=is_first_game,
                    total_games_on_slate=total_games,
                    game_index=game_idx,
                    is_last_sunday_game=is_last_sunday,
                )

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
                    ml_threshold = ML_THRESHOLDS.get(sport)
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
                    if sport == "nba":
                        # NBA: always lean underdog (backtested)
                        lean_team = away_team if current_spread < 0 else home_team
                    elif slot_type == "public":
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
        action = _build_action_string(
            lean_team, current_spread,
            matched_game["home_team"] if matched_game else None,
            moneyline_recommend,
        )

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
@require_auth
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
@require_auth
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


@app.route("/api/close-lines", methods=["POST"])
@require_auth
def api_close_lines():
    """Fetch closing lines for pending predictions."""
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "").lower() or None
        if sport and sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = None
        result = tracker.fetch_closing_lines(sport)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/model-health", methods=["GET"])
@require_auth
def api_model_health():
    """Aggregated model health across all sports."""
    if not HAS_TEST_MODEL:
        return jsonify({"success": True, "sports": {}, "message": "Test model module not available"})
    try:
        sports_data = {}
        for sport in ("nba", "nhl", "nfl", "cfb", "cbb"):
            rules_run = tm_db.get_latest_model_run(sport, "rules_backtest")
            wf_run = tm_db.get_latest_model_run(sport, "walkforward")
            conf = DATA_CONFIDENCE_LEVELS.get(sport, {})

            entry = {
                "data_confidence": conf,
                "last_backtest_date": None,
                "last_walkforward_date": None,
                "in_sample": None,
                "out_of_sample": None,
                "overfit_gap": None,
                "calibration_ece": None,
                "clv_avg": None,
            }

            if rules_run:
                entry["last_backtest_date"] = rules_run.get("run_date")
                acc = rules_run.get("accuracy")
                roi = rules_run.get("roi")
                clv = rules_run.get("clv_avg")
                entry["clv_avg"] = clv

                in_sample = {"accuracy": acc, "roi": roi}

                # Extract strong play stats from threshold_analysis
                ta = rules_run.get("threshold_analysis") or {}
                strong_data = ta.get("STRONG PLAY") or ta.get("strong") or {}
                strong_n = strong_data.get("total", 0) or strong_data.get("n", 0)
                strong_wins = strong_data.get("wins", 0)
                strong_acc = strong_data.get("win_rate") or strong_data.get("accuracy")
                if strong_n > 0:
                    if strong_wins == 0 and strong_acc:
                        strong_wins = round(strong_acc / 100 * strong_n)
                    ci = wilson_interval(strong_wins, strong_n)
                    in_sample["strong_accuracy"] = strong_acc
                    in_sample["strong_n"] = strong_n
                    in_sample["strong_ci"] = list(ci)

                # Calibration ECE from model_params
                mp = rules_run.get("model_params") or {}
                cal = mp.get("calibration") or {}
                if cal.get("ece") is not None:
                    entry["calibration_ece"] = cal["ece"]

                entry["in_sample"] = in_sample

            if wf_run:
                entry["last_walkforward_date"] = wf_run.get("run_date")
                oos_acc = wf_run.get("accuracy")
                oos_roi = wf_run.get("roi")

                out_of_sample = {"accuracy": oos_acc, "roi": oos_roi}

                # Extract CIs from walkforward model_params
                wf_params = wf_run.get("model_params") or {}
                cis = wf_params.get("confidence_intervals") or {}
                if cis.get("strong_accuracy_ci"):
                    out_of_sample["strong_ci"] = cis["strong_accuracy_ci"]
                strong_oos = cis.get("strong_accuracy")
                if strong_oos is not None:
                    out_of_sample["strong_accuracy"] = strong_oos
                strong_oos_n = cis.get("strong_n")
                if strong_oos_n is not None:
                    out_of_sample["strong_n"] = strong_oos_n

                entry["out_of_sample"] = out_of_sample

                # Compute overfit gap
                if entry["in_sample"] and oos_acc is not None:
                    is_acc = entry["in_sample"].get("accuracy")
                    if is_acc is not None:
                        entry["overfit_gap"] = round(is_acc - oos_acc, 1)

            sports_data[sport] = entry

        return jsonify({"success": True, "sports": sports_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Test Model API Endpoints ──────────────────────────────────────────────

def _is_admin():
    email = getattr(request, "user_email", "")
    if not ADMIN_EMAILS:
        return True  # No allowlist configured = everyone is admin
    return email.lower() in ADMIN_EMAILS


def _require_test_model():
    if not HAS_TEST_MODEL:
        return jsonify({"success": False, "error": "Test model module not available"}), 501
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin access required"}), 403
    return None


@app.route("/api/tm/collect", methods=["POST"])
@require_auth
def api_tm_collect():
    """Start background historical data collection for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        started = start_collection_thread(sport)
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/collect/status", methods=["GET"])
@require_auth
def api_tm_collect_status():
    """Poll collection progress for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        progress = get_collection_status(sport)
        db_progress = tm_db.get_collection_progress(sport)
        total_games = tm_db.count_historical_games(sport)
        games_with_spreads = tm_db.count_games_with_spreads(sport)
        return jsonify({
            "success": True,
            "progress": progress,
            "db_progress": db_progress,
            "total_games": total_games,
            "games_with_spreads": games_with_spreads,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/features", methods=["POST"])
@require_auth
def api_tm_features():
    """Compute features for all collected historical data."""
    err = _require_test_model()
    if err:
        return err
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        count = compute_all_features(sport)
        return jsonify({"success": True, "features_computed": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/backtest", methods=["POST"])
@require_auth
def api_tm_backtest():
    """Start background walk-forward backtest for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        started = start_backtest_thread(sport)
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/backtest/status", methods=["GET"])
@require_auth
def api_tm_backtest_status():
    """Poll backtest progress for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        progress = get_backtest_status(sport)
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/scan", methods=["POST"])
@require_auth
def api_tm_scan():
    """Scan today's games with ML model overlay."""
    err = _require_test_model()
    if err:
        return err
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        results = scan_today_with_model(sport)
        return jsonify({"success": True, "games": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/metrics", methods=["GET"])
@require_auth
def api_tm_metrics():
    """Get backtest performance metrics for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        metrics = tm_db.get_backtest_metrics(sport)
        total_games = tm_db.count_historical_games(sport)
        total_features = tm_db.count_game_features(sport)
        return jsonify({
            "success": True,
            "metrics": metrics,
            "total_games": total_games,
            "total_features": total_features,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/rules-backtest", methods=["POST"])
@require_auth
def api_tm_rules_backtest():
    """Start background rules-based replay backtest for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        started = start_rules_backtest_thread(sport)
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/rules-backtest/status", methods=["GET"])
@require_auth
def api_tm_rules_backtest_status():
    """Poll rules backtest progress for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        progress = get_rules_backtest_status(sport)
        # Hot-reload calibration when backtest completes
        if progress.get("status") == "complete":
            cal_metrics = progress.get("metrics", {})
            cal_data = cal_metrics.get("calibration")
            if cal_data:
                load_calibration(sport, cal_data)
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/rules-backtest/metrics", methods=["GET"])
@require_auth
def api_tm_rules_backtest_metrics():
    """Get rules backtest metrics with optional ML comparison."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        rules_metrics = tm_db.get_latest_model_run(sport, "rules_backtest")
        ml_metrics = tm_db.get_latest_model_run(sport, "backtest")
        return jsonify({
            "success": True,
            "rules_metrics": rules_metrics,
            "ml_metrics": ml_metrics,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/calibration", methods=["GET"])
@require_auth
def api_tm_calibration():
    """Get calibration analysis for a sport from latest rules backtest."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        run = tm_db.get_latest_model_run(sport, "rules_backtest")
        if not run or not run.get("model_params"):
            return jsonify({"success": True, "calibration": None})
        cal = run["model_params"].get("calibration")
        return jsonify({"success": True, "calibration": cal})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/walkforward", methods=["POST"])
@require_auth
def api_tm_walkforward():
    """Start background walk-forward validation for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        mode = data.get("mode", "split").lower()
        if mode not in ("split", "rolling"):
            mode = "split"
        started = start_walkforward_thread(sport, mode)
        return jsonify({"success": True, "started": started, "mode": mode})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/walkforward/status", methods=["GET"])
@require_auth
def api_tm_walkforward_status():
    """Poll walk-forward validation progress for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        progress = get_walkforward_status(sport)
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/walkforward/metrics", methods=["GET"])
@require_auth
def api_tm_walkforward_metrics():
    """Get walk-forward validation metrics with rules backtest comparison."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        wf_metrics = tm_db.get_latest_model_run(sport, "walkforward")
        rules_metrics = tm_db.get_latest_model_run(sport, "rules_backtest")
        return jsonify({
            "success": True,
            "walkforward_metrics": wf_metrics,
            "rules_metrics": rules_metrics,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = "PORT" not in os.environ
    app.run(host="0.0.0.0", port=port, debug=debug)
