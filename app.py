import os
from dotenv import load_dotenv
load_dotenv()  # Load .env before any module reads os.environ

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory
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
    scan_all_games, get_game_props, get_top_props, get_top_props_with_ev,
    classify_game_slot, _build_action_string,
)
import tracker
import bet_tracker
import pick_curation
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

REACT_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
app = Flask(__name__, static_folder=None)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
tracker.init_db()
bet_tracker.init_tracked_bets_db()
pick_curation.init_pick_approvals_db()
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

    # Load NBA EV model if available and validated
    try:
        from nba_ev_model import load_nba_ev_model, load_live_team_state as nba_load_state
        from constants import EV_CONFIG
        _ev_run = tm_db.get_latest_model_run("nba", "ev_logistic")
        if _ev_run and _ev_run.get("model_params"):
            _ev_params = _ev_run["model_params"]
            if _ev_params.get("auc", 0) >= EV_CONFIG["auc_gate"]:
                load_nba_ev_model(_ev_params)
                nba_load_state()
    except Exception as _ev_err:
        print(f"[nba_ev] Startup load skipped: {_ev_err}", flush=True)

    # Load NHL EV model if available and validated
    try:
        from nhl_ev_model import load_nhl_ev_model, load_live_team_state as nhl_load_state, NHL_EV_CONFIG
        _nhl_ev_run = tm_db.get_latest_model_run("nhl", "ev_logistic")
        if _nhl_ev_run and _nhl_ev_run.get("model_params"):
            _nhl_ev_params = _nhl_ev_run["model_params"]
            _nhl_auc = _nhl_ev_params.get("mean_auc") or _nhl_ev_params.get("auc", 0)
            if _nhl_auc >= NHL_EV_CONFIG["auc_gate"]:
                load_nhl_ev_model(_nhl_ev_params)
                nhl_load_state()
    except Exception as _nhl_ev_err:
        print(f"[nhl_ev] Startup load skipped: {_nhl_ev_err}", flush=True)

    # Load CBB EV model if available and validated
    try:
        from cbb_ev_model import load_cbb_ev_model, load_live_team_state as cbb_load_state, CBB_EV_CONFIG
        _cbb_ev_run = tm_db.get_latest_model_run("cbb", "ev_logistic")
        if _cbb_ev_run and _cbb_ev_run.get("model_params"):
            _cbb_ev_params = _cbb_ev_run["model_params"]
            _cbb_auc = _cbb_ev_params.get("mean_auc") or _cbb_ev_params.get("auc", 0)
            if _cbb_auc >= CBB_EV_CONFIG["auc_gate"]:
                load_cbb_ev_model(_cbb_ev_params)
                cbb_load_state()
    except Exception as _cbb_ev_err:
        print(f"[cbb_ev] Startup load skipped: {_cbb_ev_err}", flush=True)
scan_cache.init()

# ─── Supabase Auth ──────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "chance.kelly2003@gmail.com").split(",") if e.strip()}

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
    return send_from_directory(REACT_DIST, "index.html")


@app.route("/auth/<path:subpath>")
def auth_redirect(subpath):
    """Handle Supabase email confirmation/callback redirects."""
    return send_from_directory(REACT_DIST, "index.html")


# Legacy static assets (old app.js, style.css still served from /static/)
@app.route("/static/<path:filename>")
def legacy_static(filename):
    legacy_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    return send_from_directory(legacy_dir, filename)


# PWA assets
@app.route("/manifest.json")
def manifest():
    return send_from_directory(REACT_DIST, "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory(REACT_DIST, "sw.js")


@app.route("/icons/<path:filename>")
def icons(filename):
    icons_dir = os.path.join(REACT_DIST, "icons")
    return send_from_directory(icons_dir, filename)


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
    Admin sees all picks with approval controls; non-admin sees all picks.
    """
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        featured_only = data.get("featured_only", False)
        is_admin = _is_admin()

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
                scan_cache.request_refresh(*sports)
            else:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = {pool.submit(scan_all_games, s): s for s in missing}
                    for future in futures:
                        s = futures[future]
                        result = future.result()
                        all_results[s] = result
                        scan_cache.put(s, result)
                        try:
                            pick_curation.sync_picks_from_scan(result, s)
                        except Exception:
                            pass

            # Apply approval filtering per sport
            filtered_results = {}
            for s, games in all_results.items():
                filtered_results[s] = _apply_approval_filter(games, s, is_admin, featured_only)

            return jsonify({"success": True, "all_sports": filtered_results,
                            "cached": not missing})

        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"

        # Check cache first
        cached, age = scan_cache.get(sport)
        if cached is not None:
            scan_cache.request_refresh(sport)
            cache_age_min = round(age / 60) if age else 0
            freshness = "fresh" if cache_age_min < 30 else ("aging" if cache_age_min < 120 else "stale")
            games = _apply_approval_filter(cached, sport, is_admin, featured_only)
            if games is None:
                return jsonify({"success": True, "games": [],
                                "picks_pending_review": True})
            return jsonify({
                "success": True, "games": games,
                "cached": True, "cache_age": round(age),
                "signal_freshness": freshness,
                "scan_age_minutes": cache_age_min,
                "featured_mode": featured_only,
            })

        # No cache — blocking scan
        results = scan_all_games(sport)
        scan_cache.put(sport, results)
        try:
            pick_curation.sync_picks_from_scan(results, sport)
        except Exception:
            pass
        games = _apply_approval_filter(results, sport, is_admin, featured_only)
        if games is None:
            return jsonify({"success": True, "games": [],
                            "picks_pending_review": True})
        return jsonify({"success": True, "games": games, "featured_mode": featured_only})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _today_est():
    """Return today's date string in EST (UTC-5)."""
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d")


def _apply_approval_filter(games, sport, is_admin, featured_only=False):
    """
    Filter scan results based on admin approval status.
    Admin: annotate games with approval_status.
    Non-admin: see all games, or only approved if featured_only=True.
    """
    if not games:
        return games

    game_date = _today_est()
    event_ids = [str(g.get("event_id", "")) for g in games]
    approval_map = pick_curation.get_approval_map(event_ids, sport, game_date)

    if is_admin:
        for g in games:
            eid = str(g.get("event_id", ""))
            ap = approval_map.get(eid, {})
            g["approval_status"] = ap.get("status", "")
            g["admin_notes"] = ap.get("admin_notes", "")
            if ap.get("admin_lean_override"):
                g["admin_lean_override"] = ap["admin_lean_override"]
            if ap.get("admin_confidence_override") is not None:
                g["admin_confidence_override"] = ap["admin_confidence_override"]
        # Admin sees all games (with annotations) unless featured_only is True
        if featured_only:
            approved_ids = pick_curation.get_approved_event_ids(sport, game_date)
            games = [g for g in games if str(g.get("event_id", "")) in approved_ids]
        return games

    # Non-admin: return all games or only approved if featured_only
    if featured_only:
        approved_ids = pick_curation.get_approved_event_ids(sport, game_date)
        filtered = []
        for g in games:
            eid = str(g.get("event_id", ""))
            if eid in approved_ids:
                ap = approval_map.get(eid, {})
                if ap.get("admin_lean_override"):
                    g["lean_team"] = ap["admin_lean_override"]
                if ap.get("admin_confidence_override") is not None:
                    g["cover_pct"] = ap["admin_confidence_override"]
                filtered.append(g)
        return filtered
    else:
        # Apply admin overrides if they exist
        for g in games:
            eid = str(g.get("event_id", ""))
            ap = approval_map.get(eid, {})
            if ap.get("admin_lean_override"):
                g["lean_team"] = ap["admin_lean_override"]
            if ap.get("admin_confidence_override") is not None:
                g["cover_pct"] = ap["admin_confidence_override"]
        return games


@app.route("/api/props", methods=["GET"])
@require_auth
def api_props():
    """On-demand PRISM player props for a single game."""
    from concurrent.futures import TimeoutError as FuturesTimeoutError
    from concurrent.futures import ThreadPoolExecutor
    import time

    try:
        event_id = request.args.get("event_id", "")
        sport = request.args.get("sport", "nba").lower()
        if not event_id:
            return jsonify({"success": False, "error": "event_id required"}), 400
        if sport not in ("nba", "cbb"):
            return jsonify({"success": True, "props": []})

        # Run with timeout to prevent indefinite hangs
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(get_game_props, event_id, sport)
            try:
                props = future.result(timeout=15)  # 15 second timeout
                elapsed = time.time() - start_time
                print(f"[api_props] Loaded props for {event_id} in {elapsed:.2f}s", flush=True)
                return jsonify({"success": True, "props": props})
            except FuturesTimeoutError:
                print(f"[api_props] Timeout loading props for {event_id}", flush=True)
                return jsonify({"success": False, "error": "Request timeout - try again"}), 504
    except Exception as e:
        print(f"[api_props] Error: {e}", flush=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/lines", methods=["GET"])
@require_auth
def api_lines():
    """Fetch per-book spreads and totals for Line Shop."""
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        from api_odds import get_multibook_lines
        lines = get_multibook_lines(sport)
        return jsonify({"success": True, "lines": lines})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/top-props", methods=["GET"])
@require_auth
def api_top_props():
    """Generate PRISM player props for ALL today's games at once."""
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "cbb"):
            return jsonify({"success": True, "props": []})

        # Check persistent cache first
        import cache_manager
        cached_props = cache_manager.get_cached_props(sport, cache_minutes=10)
        if cached_props is not None:
            return jsonify({"success": True, "props": cached_props, "cached": True})

        # Cache miss - compute fresh
        props = get_top_props(sport)

        # Even if no props found, cache empty result to avoid hammering APIs
        cache_manager.cache_props(sport, props)

        return jsonify({"success": True, "props": props, "cached": False})
    except Exception as e:
        # Log detailed error for debugging
        import traceback
        print(f"[api_top_props] Error: {traceback.format_exc()}", flush=True)
        # Return empty props instead of 500 error (graceful degradation)
        return jsonify({"success": True, "props": [], "error": str(e)})


@app.route("/api/ev/player-props", methods=["GET"])
@require_auth
def api_ev_player_props():
    """Get player props with EV calculations for EV Engine."""
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "cbb"):
            return jsonify({"success": True, "props": []})

        # Check persistent cache first (use separate cache key for EV props)
        import cache_manager
        supabase = cache_manager._get_supabase()
        if supabase:
            try:
                from datetime import datetime, timedelta, timezone
                cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
                result = (
                    supabase.table("props_cache")
                    .select("*")
                    .eq("sport", f"{sport}_ev")
                    .gte("created_at", cutoff.isoformat())
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if result.data:
                    import json
                    cached = json.loads(result.data[0]["results"])
                    return jsonify({"success": True, "props": cached, "cached": True})
            except Exception:
                pass

        # Cache miss - compute fresh
        props = get_top_props_with_ev(sport)

        # Store in cache with _ev suffix
        if supabase:
            try:
                import json
                supabase.table("props_cache").insert({
                    "sport": f"{sport}_ev",
                    "results": json.dumps(props),
                    "created_at": datetime.now(timezone.utc).isoformat()
                }).execute()
            except Exception:
                pass

        return jsonify({"success": True, "props": props, "cached": False})
    except Exception as e:
        # Log detailed error for debugging
        import traceback
        print(f"[api_ev_player_props] Error: {traceback.format_exc()}", flush=True)
        # Return empty props instead of 500 error (graceful degradation)
        return jsonify({"success": True, "props": [], "error": str(e)})


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


@app.route("/api/clv/trend", methods=["GET"])
@require_auth
def api_clv_trend():
    """CLV time-series trend data with rolling averages and health indicators."""
    try:
        sport = request.args.get("sport", "").lower() or None
        if sport and sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = None
        trend = tracker.get_clv_trend(sport)
        return jsonify({"success": True, "trend": trend})
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

            # Model comparison (dynamic tier)
            try:
                from model_selection import get_model_comparison
                comp = get_model_comparison(sport)
                entry["model_comparison"] = comp
            except Exception:
                entry["model_comparison"] = None

            sports_data[sport] = entry

        return jsonify({"success": True, "sports": sports_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/model-comparison", methods=["GET"])
@require_auth
def api_model_comparison():
    """Compare rules vs EV model OOS performance per sport."""
    try:
        from model_selection import get_model_comparison
        sport = request.args.get("sport")
        if sport:
            comp = get_model_comparison(sport)
            return jsonify({"success": True, "comparisons": {sport: comp}})
        # All sports
        comparisons = {}
        for s in ("nba", "nhl", "nfl", "cfb", "cbb"):
            comparisons[s] = get_model_comparison(s)
        return jsonify({"success": True, "comparisons": comparisons})
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


@app.route("/api/tm/slot-validation", methods=["POST"])
@require_auth
def api_tm_slot_validation():
    """Start background slot validation for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.slot_validation import start_slot_validation_thread
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        started = start_slot_validation_thread(sport)
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/slot-validation/status", methods=["GET"])
@require_auth
def api_tm_slot_validation_status():
    """Poll slot validation progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.slot_validation import get_slot_validation_status
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        progress = get_slot_validation_status(sport)
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/slot-validation/metrics", methods=["GET"])
@require_auth
def api_tm_slot_validation_metrics():
    """Get saved slot validation results."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        if sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = "nba"
        run = tm_db.get_latest_model_run(sport, "slot_validation")
        return jsonify({"success": True, "metrics": run})
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


# ─── NBA EV Model Endpoints ───────────────────────────────────────────────

@app.route("/api/tm/nba-ev/train", methods=["POST"])
@require_auth
def api_tm_nba_ev_train():
    """Start background NBA EV model training."""
    err = _require_test_model()
    if err:
        return err
    try:
        from nba_ev_model import start_ev_training_thread
        started = start_ev_training_thread()
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-ev/status", methods=["GET"])
@require_auth
def api_tm_nba_ev_status():
    """Poll NBA EV model training progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from nba_ev_model import get_ev_training_status
        progress = get_ev_training_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-ev/metrics", methods=["GET"])
@require_auth
def api_tm_nba_ev_metrics():
    """Get latest NBA EV model metrics."""
    err = _require_test_model()
    if err:
        return err
    try:
        ev_run = tm_db.get_latest_model_run("nba", "ev_logistic")
        from nba_ev_model import is_ev_model_active
        return jsonify({
            "success": True,
            "ev_metrics": ev_run,
            "model_active": is_ev_model_active(),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── NHL EV Model Endpoints ───────────────────────────────────────────────

@app.route("/api/tm/nhl-ev/train", methods=["POST"])
@require_auth
def api_tm_nhl_ev_train():
    """Start background NHL EV model training."""
    err = _require_test_model()
    if err:
        return err
    try:
        from nhl_ev_model import start_ev_training_thread
        started = start_ev_training_thread()
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nhl-ev/status", methods=["GET"])
@require_auth
def api_tm_nhl_ev_status():
    """Poll NHL EV model training progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from nhl_ev_model import get_ev_training_status
        progress = get_ev_training_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nhl-ev/metrics", methods=["GET"])
@require_auth
def api_tm_nhl_ev_metrics():
    """Get latest NHL EV model metrics."""
    err = _require_test_model()
    if err:
        return err
    try:
        ev_run = tm_db.get_latest_model_run("nhl", "ev_logistic")
        from nhl_ev_model import is_ev_model_active
        return jsonify({
            "success": True,
            "ev_metrics": ev_run,
            "model_active": is_ev_model_active(),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── CBB EV Model Endpoints ───────────────────────────────────────────────


@app.route("/api/tm/cbb-ev/train", methods=["POST"])
@require_auth
def api_tm_cbb_ev_train():
    """Start background CBB EV model training."""
    err = _require_test_model()
    if err:
        return err
    try:
        from cbb_ev_model import start_ev_training_thread
        started = start_ev_training_thread()
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/cbb-ev/status", methods=["GET"])
@require_auth
def api_tm_cbb_ev_status():
    """Poll CBB EV model training progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from cbb_ev_model import get_ev_training_status
        progress = get_ev_training_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/cbb-ev/metrics", methods=["GET"])
@require_auth
def api_tm_cbb_ev_metrics():
    """Get latest CBB EV model metrics."""
    err = _require_test_model()
    if err:
        return err
    try:
        ev_run = tm_db.get_latest_model_run("cbb", "ev_logistic")
        from cbb_ev_model import is_ev_model_active
        return jsonify({
            "success": True,
            "ev_metrics": ev_run,
            "model_active": is_ev_model_active(),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Pick Curation (Admin) ────────────────────────────────────────────────────


@app.route("/api/picks/pending", methods=["GET"])
@require_auth
def api_picks_pending():
    """List picks for admin review."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        sport = request.args.get("sport", "nba").lower()
        game_date = request.args.get("date") or _today_est()
        picks = pick_curation.get_pending_picks(sport, game_date)
        return jsonify({"success": True, "picks": picks})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/picks/approve", methods=["POST"])
@require_auth
def api_picks_approve():
    """Approve a single pick."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        data = request.get_json(force=True)
        event_id = data.get("event_id")
        sport = data.get("sport", "nba").lower()
        game_date = data.get("game_date") or _today_est()
        notes = data.get("notes")
        lean_override = data.get("lean_override")
        confidence_override = data.get("confidence_override")
        if not event_id:
            return jsonify({"success": False, "error": "event_id required"}), 400
        pick_curation.approve_pick(event_id, sport, game_date,
                                   notes=notes, lean_override=lean_override,
                                   confidence_override=confidence_override)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/picks/reject", methods=["POST"])
@require_auth
def api_picks_reject():
    """Reject a single pick."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        data = request.get_json(force=True)
        event_id = data.get("event_id")
        sport = data.get("sport", "nba").lower()
        game_date = data.get("game_date") or _today_est()
        notes = data.get("notes")
        if not event_id:
            return jsonify({"success": False, "error": "event_id required"}), 400
        pick_curation.reject_pick(event_id, sport, game_date, notes=notes)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/picks/approve-all", methods=["POST"])
@require_auth
def api_picks_approve_all():
    """Approve all pending picks for a sport+date."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        data = request.get_json(force=True)
        sport = data.get("sport", "nba").lower()
        game_date = data.get("game_date") or _today_est()
        pick_curation.approve_all_picks(sport, game_date)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/picks/status", methods=["GET"])
@require_auth
def api_picks_status():
    """Check if admin has reviewed picks for a sport+date."""
    try:
        sport = request.args.get("sport", "nba").lower()
        game_date = request.args.get("date") or _today_est()
        reviewed = pick_curation.has_admin_reviewed(sport, game_date)
        return jsonify({"success": True, "reviewed": reviewed})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Bet Tracker (Admin) ──────────────────────────────────────────────────────


@app.route("/api/bets/save", methods=["POST"])
@require_auth
def api_bets_save():
    """Save confirmed bets from the frontend."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        data = request.get_json(force=True)
        bets = data.get("bets", [])
        if not bets:
            return jsonify({"success": False, "error": "No bets provided"}), 400
        result = bet_tracker.save_tracked_bets(bets, request.user_email)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/bets", methods=["GET"])
@require_auth
def api_bets_list():
    """List tracked bets with optional sport/status filters."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        sport = request.args.get("sport", "").lower() or None
        status = request.args.get("status", "").upper() or None
        if sport and sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = None
        if status and status not in ("PENDING", "WIN", "LOSS", "PUSH"):
            status = None
        bets = bet_tracker.get_tracked_bets(request.user_email, sport=sport, status=status)
        return jsonify({"success": True, "bets": bets})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/bets/grade", methods=["POST"])
@require_auth
def api_bets_grade():
    """Grade all PENDING bets for this user."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        result = bet_tracker.grade_tracked_bets(request.user_email)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/bets/dashboard", methods=["GET"])
@require_auth
def api_bets_dashboard():
    """Dashboard aggregation stats for tracked bets."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        sport = request.args.get("sport", "").lower() or None
        if sport and sport not in ("nba", "nhl", "cfb", "nfl", "cbb"):
            sport = None
        stats = bet_tracker.get_tracked_dashboard(request.user_email, sport=sport)
        return jsonify({"success": True, **stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/bets/<int:bet_id>", methods=["DELETE"])
@require_auth
def api_bets_delete(bet_id):
    """Delete a PENDING bet."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        deleted = bet_tracker.delete_tracked_bet(bet_id, request.user_email)
        if deleted:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Bet not found or not PENDING"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── NBA Rebuild Endpoints ───────────────────────────────────────────────


@app.route("/api/tm/nba-rebuild/base-lean", methods=["POST"])
@require_auth
def api_tm_nba_rebuild_base_lean():
    """Start background base lean validation."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.base_lean import start_base_lean_thread
        started = start_base_lean_thread()
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-rebuild/base-lean/status", methods=["GET"])
@require_auth
def api_tm_nba_rebuild_base_lean_status():
    """Poll base lean validation progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.base_lean import get_base_lean_status
        progress = get_base_lean_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-rebuild/factor-isolation", methods=["POST"])
@require_auth
def api_tm_nba_rebuild_factor_isolation():
    """Start background factor isolation testing."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.factor_isolation import start_factor_isolation_thread
        started = start_factor_isolation_thread()
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-rebuild/factor-isolation/status", methods=["GET"])
@require_auth
def api_tm_nba_rebuild_factor_isolation_status():
    """Poll factor isolation progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.factor_isolation import get_factor_isolation_status
        progress = get_factor_isolation_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-rebuild/combined", methods=["POST"])
@require_auth
def api_tm_nba_rebuild_combined():
    """Start combined model rebuild from survivors."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.combined_model import start_combined_thread
        started = start_combined_thread()
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-rebuild/combined/status", methods=["GET"])
@require_auth
def api_tm_nba_rebuild_combined_status():
    """Poll combined model rebuild progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.combined_model import get_combined_status
        progress = get_combined_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── NBA Ensemble Test ───────────────────────────────────────────────────


@app.route("/api/tm/nba-rebuild/ensemble", methods=["POST"])
@require_auth
def api_tm_nba_rebuild_ensemble():
    """Start ensemble test (EV-only vs rules-only vs combined)."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.ensemble_test import start_ensemble_thread
        started = start_ensemble_thread()
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-rebuild/ensemble/status", methods=["GET"])
@require_auth
def api_tm_nba_rebuild_ensemble_status():
    """Poll ensemble test progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.ensemble_test import get_ensemble_status
        progress = get_ensemble_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Data Quality Report ─────────────────────────────────────────────────


@app.route("/api/tm/data-quality", methods=["GET"])
@require_auth
def api_tm_data_quality():
    """Get data quality/completeness report for a sport."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba").lower()
        from test_model.data_quality import _data_quality_report
        report = _data_quality_report(sport)
        return jsonify({"success": True, **report})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── PRISM Auto-Tracking Endpoints ───────────────────────────────────────


@app.route("/api/prism/grade", methods=["POST"])
@require_auth
def api_prism_grade():
    """Grade PENDING PRISM predictions against actual outcomes."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        result = tracker.grade_prism_predictions(sport)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/prism/dashboard", methods=["GET"])
@require_auth
def api_prism_dashboard():
    """PRISM prediction accuracy dashboard with Wilson CI."""
    if not _is_admin():
        return jsonify({"success": False, "error": "Admin only"}), 403
    try:
        sport = request.args.get("sport", "nba").lower()
        stats = tracker.get_prism_dashboard(sport)
        return jsonify({"success": True, **stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── NBA Calibration Check ────────────────────────────────────────────────


@app.route("/api/tm/nba-rebuild/calibration", methods=["POST"])
@require_auth
def api_tm_nba_rebuild_calibration():
    """Start calibration validation for NBA predictions."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.calibration_check import start_calibration_thread
        started = start_calibration_thread()
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/nba-rebuild/calibration/status", methods=["GET"])
@require_auth
def api_tm_nba_rebuild_calibration_status():
    """Poll calibration validation progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.nba_rebuild.calibration_check import get_calibration_status
        progress = get_calibration_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── PRISM Backtest Endpoints ─────────────────────────────────────────────


@app.route("/api/tm/prism-backtest", methods=["POST"])
@require_auth
def api_tm_prism_backtest():
    """Start PRISM accuracy backtest."""
    err = _require_test_model()
    if err:
        return err
    try:
        data = request.get_json(silent=True) or {}
        sport = data.get("sport", "nba").lower()
        from test_model.prism_backtest import start_prism_backtest_thread
        started = start_prism_backtest_thread(sport)
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/prism-backtest/status", methods=["GET"])
@require_auth
def api_tm_prism_backtest_status():
    """Poll PRISM backtest progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        from test_model.prism_backtest import get_prism_backtest_status
        progress = get_prism_backtest_status()
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Injury Backfill API ──────────────────────────────────────────────────────

@app.route("/api/tm/injury-backfill", methods=["POST"])
@require_auth
def api_tm_injury_backfill():
    """Start background injury backfill from box scores."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.json.get("sport", "nba") if request.json else "nba"
        if sport not in ("nba", "nhl", "cbb"):
            return jsonify({"success": False, "error": "Injury backfill only supports nba, nhl, cbb"}), 400
        from test_model.injury_backfill import start_backfill_thread
        started = start_backfill_thread(sport)
        return jsonify({"success": True, "started": started})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/tm/injury-backfill/status", methods=["GET"])
@require_auth
def api_tm_injury_backfill_status():
    """Poll injury backfill progress."""
    err = _require_test_model()
    if err:
        return err
    try:
        sport = request.args.get("sport", "nba")
        from test_model.injury_backfill import get_backfill_status
        progress = get_backfill_status(sport)
        return jsonify({"success": True, "progress": progress})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── React SPA catch-all (must be last) ───────────────────────────────────────
# Serves index.html for any non-API, non-static path so React Router handles it.

@app.route("/<path:path>")
def react_catchall(path):
    # If the path points to an actual file in dist, serve it (e.g. assets/*, favicon.ico)
    file_path = os.path.join(REACT_DIST, path)
    if os.path.isfile(file_path):
        return send_from_directory(REACT_DIST, path)
    # Otherwise fall through to React Router
    return send_from_directory(REACT_DIST, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = "PORT" not in os.environ
    app.run(host="0.0.0.0", port=port, debug=debug)
