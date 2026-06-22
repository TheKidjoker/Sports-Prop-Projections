import sqlite3
import os
import requests
from datetime import datetime, timezone
from constants import wilson_interval, metric_with_ci, MIN_SAMPLES

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.db")

ODDS_API_SPORT_KEYS = {
    "nba": "basketball_nba",
    "nhl": "icehockey_nhl",
    "nfl": "americanfootball_nfl",
    "cfb": "americanfootball_ncaaf",
    "cbb": "basketball_ncaab",
}

# ─── Supabase singleton ──────────────────────────────────────────────────────
_supabase_client = None


def _use_supabase():
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# ─── SQLite helpers ───────────────────────────────────────────────────────────

def _get_sqlite():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates predictions table if it doesn't exist (SQLite only; Supabase uses DDL)."""
    if _use_supabase():
        return  # Table already exists in Supabase
    conn = _get_sqlite()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            game_date TEXT,
            game_time_est TEXT,
            lean_team TEXT,
            action TEXT,
            slot_type TEXT,
            recommendation TEXT,
            confirmation_score REAL,
            cover_pct REAL,
            current_spread REAL,
            result TEXT DEFAULT 'PENDING',
            home_score INTEGER,
            away_score INTEGER,
            created_at TEXT,
            graded_at TEXT,
            UNIQUE(event_id, sport)
        )
    """)
    _migrate_add_column(cur, "game_date")
    _migrate_add_column(cur, "line_at_pick REAL")
    _migrate_add_column(cur, "closing_line REAL")
    _migrate_add_column(cur, "clv REAL")
    _migrate_add_column(cur, "clv_direction INTEGER")

    # PRISM predictions table for auto-tracking
    cur.execute("""
        CREATE TABLE IF NOT EXISTS prism_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            player_name TEXT NOT NULL,
            stat_type TEXT NOT NULL,
            projection REAL,
            line REAL,
            line_source TEXT,
            edge REAL,
            signal TEXT,
            confidence REAL,
            slot_type TEXT,
            result TEXT DEFAULT 'PENDING',
            actual_value REAL,
            created_at TEXT,
            graded_at TEXT,
            UNIQUE(event_id, sport, player_name, stat_type)
        )
    """)
    # Prop EV columns on prism_predictions
    for col_def in (
        "std_dev REAL", "z_score REAL", "model_probability REAL",
        "over_odds INTEGER", "under_odds INTEGER",
        "implied_probability REAL", "expected_value REAL", "edge_pct REAL",
    ):
        try:
            cur.execute(f"ALTER TABLE prism_predictions ADD COLUMN {col_def}")
        except Exception:
            pass
    conn.commit()
    cur.close()
    conn.close()


def _migrate_add_column(cur, column_def):
    """Adds a column to predictions table if it doesn't already exist (SQLite only).
    column_def can be just a name (defaults to TEXT) or 'name TYPE'."""
    if " " not in column_def.strip():
        column_def = column_def + " TEXT"
    try:
        cur.execute(f"ALTER TABLE predictions ADD COLUMN {column_def}")
    except Exception:
        pass


# ─── save_predictions ─────────────────────────────────────────────────────────

def save_predictions(games, sport):
    """
    Upserts qualifying games into the predictions table.
    Qualifying: cover_pct >= 68.5, has lean_team + action, not skip.
    """
    now = datetime.now(timezone.utc).isoformat()

    rows_to_save = []
    for g in games:
        if g.get("skip"):
            continue
        if (g.get("cover_pct") or 0) < 68.5:
            continue
        if not g.get("lean_team") or not g.get("action"):
            continue

        game_date_display = ""
        raw_date = g.get("game_date", "")
        if raw_date:
            try:
                from datetime import timedelta as _td
                gdt = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                est_dt = gdt - _td(hours=5)
                game_date_display = est_dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass

        rows_to_save.append({
            "event_id": g.get("event_id"),
            "sport": sport,
            "home_team": g.get("home_team"),
            "away_team": g.get("away_team"),
            "game_date": game_date_display,
            "game_time_est": g.get("game_time_est", ""),
            "lean_team": g.get("lean_team"),
            "action": g.get("action"),
            "slot_type": g.get("slot_type", ""),
            "recommendation": g.get("recommendation", ""),
            "confirmation_score": g.get("confirmation_score", 0),
            "cover_pct": g.get("cover_pct", 0),
            "current_spread": g.get("current_spread"),
            "line_at_pick": g.get("current_spread"),
            "created_at": now,
        })

    if not rows_to_save:
        return

    if _use_supabase():
        sb = _get_supabase()
        sb.table("predictions").upsert(
            rows_to_save, on_conflict="event_id,sport"
        ).execute()
        # Preserve immutable line_at_pick — only set on first insert
        sb.table("predictions").update(
            {"line_at_pick": None}
        ).is_("line_at_pick", "null").execute()
        # Actually: set line_at_pick = current_spread where it's still null
        for row in rows_to_save:
            sb.table("predictions").update(
                {"line_at_pick": row["current_spread"]}
            ).eq("event_id", row["event_id"]).eq("sport", row["sport"]).is_("line_at_pick", "null").execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        for row in rows_to_save:
            cur.execute("""
                INSERT INTO predictions
                    (event_id, sport, home_team, away_team, game_date, game_time_est,
                     lean_team, action, slot_type, recommendation,
                     confirmation_score, cover_pct, current_spread, line_at_pick, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, sport) DO UPDATE SET
                    lean_team = EXCLUDED.lean_team,
                    action = EXCLUDED.action,
                    slot_type = EXCLUDED.slot_type,
                    recommendation = EXCLUDED.recommendation,
                    confirmation_score = EXCLUDED.confirmation_score,
                    cover_pct = EXCLUDED.cover_pct,
                    current_spread = EXCLUDED.current_spread,
                    game_date = EXCLUDED.game_date
            """, (
                row["event_id"], row["sport"], row["home_team"], row["away_team"],
                row["game_date"], row["game_time_est"], row["lean_team"],
                row["action"], row["slot_type"], row["recommendation"],
                row["confirmation_score"], row["cover_pct"],
                row["current_spread"], row["line_at_pick"], row["created_at"],
            ))
        conn.commit()
        cur.close()
        conn.close()


# ─── grade_predictions ────────────────────────────────────────────────────────

def grade_predictions(sport=None):
    """
    Grades PENDING predictions by fetching final scores from ESPN.
    Fetches closing lines as a safety net before grading.
    Returns dict with graded count and summary.
    """
    from api_client import get_game_final_score

    # Safety net: capture closing lines for any predictions still missing them
    try:
        fetch_closing_lines(sport)
    except Exception:
        pass

    graded = 0
    results_summary = {"hit": 0, "miss": 0, "push": 0, "not_final": 0}

    if _use_supabase():
        sb = _get_supabase()
        query = sb.table("predictions").select("*").eq("result", "PENDING")
        if sport:
            query = query.eq("sport", sport)
        rows = query.execute().data

        for row in rows:
            home_score, away_score, is_final = get_game_final_score(
                row["event_id"], row["sport"]
            )
            if not is_final:
                results_summary["not_final"] += 1
                continue

            result = _determine_result(
                row["lean_team"], row["home_team"], row["away_team"],
                row["current_spread"], row["action"],
                home_score, away_score,
            )
            now = datetime.now(timezone.utc).isoformat()
            sb.table("predictions").update({
                "result": result,
                "home_score": home_score,
                "away_score": away_score,
                "graded_at": now,
            }).eq("id", row["id"]).execute()

            graded += 1
            results_summary[result.lower()] = results_summary.get(result.lower(), 0) + 1
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        if sport:
            cur.execute(
                "SELECT * FROM predictions WHERE result = 'PENDING' AND sport = ?",
                (sport,)
            )
        else:
            cur.execute("SELECT * FROM predictions WHERE result = 'PENDING'")

        rows = [dict(row) for row in cur.fetchall()]

        for row in rows:
            home_score, away_score, is_final = get_game_final_score(
                row["event_id"], row["sport"]
            )
            if not is_final:
                results_summary["not_final"] += 1
                continue

            result = _determine_result(
                row["lean_team"], row["home_team"], row["away_team"],
                row["current_spread"], row["action"],
                home_score, away_score,
            )
            now = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "UPDATE predictions SET result = ?, home_score = ?, away_score = ?, graded_at = ? WHERE id = ?",
                (result, home_score, away_score, now, row["id"])
            )
            graded += 1
            results_summary[result.lower()] = results_summary.get(result.lower(), 0) + 1

        conn.commit()
        cur.close()
        conn.close()

    return {"graded": graded, "summary": results_summary}


def _determine_result(lean_team, home_team, away_team, spread, action,
                      home_score, away_score):
    """
    Grades a prediction as HIT, MISS, or PUSH.

    ATS: if lean=home, HIT when home_score + spread > away_score
    Moneyline: straight win/loss
    PUSH on exact tie
    """
    if action and "Moneyline" in action:
        if lean_team == home_team:
            if home_score > away_score:
                return "HIT"
            elif home_score == away_score:
                return "PUSH"
            else:
                return "MISS"
        else:
            if away_score > home_score:
                return "HIT"
            elif away_score == home_score:
                return "PUSH"
            else:
                return "MISS"

    if spread is None:
        if lean_team == home_team:
            return "HIT" if home_score > away_score else "MISS"
        else:
            return "HIT" if away_score > home_score else "MISS"

    if lean_team == home_team:
        adjusted = home_score + spread
        if adjusted > away_score:
            return "HIT"
        elif adjusted == away_score:
            return "PUSH"
        else:
            return "MISS"
    else:
        adjusted = away_score - spread
        if adjusted > home_score:
            return "HIT"
        elif adjusted == home_score:
            return "PUSH"
        else:
            return "MISS"


# ─── get_dashboard_stats ──────────────────────────────────────────────────────

def get_dashboard_stats(sport=None, start_date=None, end_date=None):
    """
    Returns aggregated dashboard stats.
    Auto-grades all pending predictions before computing stats.

    Args:
        sport: Optional sport filter
        start_date: Optional start date (YYYY-MM-DD) for filtering
        end_date: Optional end date (YYYY-MM-DD) for filtering
    """
    try:
        grade_predictions(sport)
    except Exception:
        pass

    if _use_supabase():
        return _dashboard_supabase(sport)
    else:
        return _dashboard_sqlite(sport, start_date=start_date, end_date=end_date)


def _dashboard_supabase(sport=None):
    sb = _get_supabase()

    # Overall aggregation via RPC
    overall = _aggregate_stats_supabase(None, None, sport)

    # Get distinct sports
    query = sb.table("predictions").select("sport")
    if sport:
        query = query.eq("sport", sport)
    all_rows = query.execute().data
    distinct_sports = list({r["sport"] for r in all_rows})

    by_sport = []
    for s in distinct_sports:
        stats = _aggregate_stats_supabase(None, None, s)
        stats["sport"] = s
        by_sport.append(stats)

    # Get distinct slot types
    slots_rows = sb.table("predictions").select("slot_type").neq("slot_type", "")
    if sport:
        slots_rows = slots_rows.eq("sport", sport)
    slots_rows = slots_rows.execute().data
    distinct_slots = list({r["slot_type"] for r in slots_rows if r["slot_type"]})

    by_slot = []
    for sl in distinct_slots:
        stats = _aggregate_stats_supabase("slot_type", sl, sport)
        stats["slot_type"] = sl
        by_slot.append(stats)

    # Get distinct recommendations
    recs_rows = sb.table("predictions").select("recommendation").neq("recommendation", "")
    if sport:
        recs_rows = recs_rows.eq("sport", sport)
    recs_rows = recs_rows.execute().data
    distinct_recs = list({r["recommendation"] for r in recs_rows if r["recommendation"]})

    by_recommendation = []
    for rec in distinct_recs:
        stats = _aggregate_stats_supabase("recommendation", rec, sport)
        stats["recommendation"] = rec
        by_recommendation.append(stats)

    # All predictions, newest first
    recent_q = sb.table("predictions").select("*").order("created_at", desc=True)
    if sport:
        recent_q = recent_q.eq("sport", sport)
    recent = recent_q.execute().data

    clv = _compute_clv_metrics(recent)

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_slot": by_slot,
        "by_recommendation": by_recommendation,
        "recent": recent,
        "clv": clv,
    }


def _aggregate_stats_supabase(where_column, where_value, sport=None):
    """Call the aggregate_prediction_stats RPC function in Supabase."""
    sb = _get_supabase()
    resp = sb.rpc("aggregate_prediction_stats", {
        "p_where_column": where_column,
        "p_where_value": where_value,
        "p_sport": sport,
    }).execute()

    row = resp.data[0] if resp.data else {}
    wins = row.get("wins", 0) or 0
    losses = row.get("losses", 0) or 0
    pushes = row.get("pushes", 0) or 0
    pending = row.get("pending", 0) or 0
    total = row.get("total", 0) or 0

    denominator = wins + losses
    win_rate = round((wins / denominator) * 100, 1) if denominator > 0 else 0
    ci = metric_with_ci(wins, denominator, min_sample=MIN_SAMPLES["overall"])

    return {
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "pending": pending,
        "total": total,
        "win_rate": win_rate,
        "win_rate_ci": ci,
    }


def _dashboard_sqlite(sport=None, start_date=None, end_date=None):
    conn = _get_sqlite()
    cur = conn.cursor()

    sport_filter = ""
    params = []
    if sport:
        sport_filter = " AND sport = ?"
        params = [sport]

    # Date range filtering
    date_filter = ""
    date_params = []
    if start_date:
        date_filter += " AND game_date >= ?"
        date_params.append(start_date)
    if end_date:
        date_filter += " AND game_date <= ?"
        date_params.append(end_date)

    combined_filter = sport_filter + date_filter
    combined_params = params + date_params

    overall = _aggregate_stats_sqlite(cur, combined_filter, combined_params)

    # By sport
    cur.execute(
        "SELECT DISTINCT sport FROM predictions WHERE 1=1" + combined_filter,
        combined_params
    )
    sports = [dict(row) for row in cur.fetchall()]
    by_sport = []
    for s in sports:
        sp_params = [s["sport"]] + date_params
        stats = _aggregate_stats_sqlite(cur, " AND sport = ?" + date_filter, sp_params)
        stats["sport"] = s["sport"]
        by_sport.append(stats)

    # By slot
    cur.execute(
        "SELECT DISTINCT slot_type FROM predictions WHERE slot_type != ''" + combined_filter,
        combined_params
    )
    slots = [dict(row) for row in cur.fetchall()]
    by_slot = []
    for s in slots:
        slot_params = [s["slot_type"]] + combined_params
        stats = _aggregate_stats_sqlite(cur, " AND slot_type = ?" + combined_filter, slot_params)
        stats["slot_type"] = s["slot_type"]
        by_slot.append(stats)

    # By recommendation
    cur.execute(
        "SELECT DISTINCT recommendation FROM predictions WHERE recommendation != ''" + combined_filter,
        combined_params
    )
    recs = [dict(row) for row in cur.fetchall()]
    by_recommendation = []
    for r in recs:
        rec_params = [r["recommendation"]] + combined_params
        stats = _aggregate_stats_sqlite(cur, " AND recommendation = ?" + combined_filter, rec_params)
        stats["recommendation"] = r["recommendation"]
        by_recommendation.append(stats)

    # Recent
    cur.execute(
        "SELECT * FROM predictions WHERE 1=1" + combined_filter +
        " ORDER BY created_at DESC",
        combined_params
    )
    recent = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    clv = _compute_clv_metrics(recent)

    # Drawdown, variance, streak analytics
    drawdown = compute_drawdown_metrics(recent)
    variance = compute_variance_metrics(recent)
    streaks = compute_streak_analysis(recent)
    monthly_breakdown = get_performance_by_period(recent)

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_slot": by_slot,
        "by_recommendation": by_recommendation,
        "recent": recent,
        "clv": clv,
        "drawdown": drawdown,
        "variance": variance,
        "streaks": streaks,
        "monthly_breakdown": monthly_breakdown,
    }


def _aggregate_stats_sqlite(cur, where_extra="", params=None):
    if params is None:
        params = []

    cur.execute(
        "SELECT "
        "  SUM(CASE WHEN result = 'HIT' THEN 1 ELSE 0 END) as wins, "
        "  SUM(CASE WHEN result = 'MISS' THEN 1 ELSE 0 END) as losses, "
        "  SUM(CASE WHEN result = 'PUSH' THEN 1 ELSE 0 END) as pushes, "
        "  SUM(CASE WHEN result = 'PENDING' THEN 1 ELSE 0 END) as pending, "
        "  COUNT(*) as total "
        "FROM predictions WHERE 1=1" + where_extra,
        params
    )
    row = cur.fetchone()
    if row:
        row = dict(row)

    wins = (row["wins"] or 0) if row else 0
    losses = (row["losses"] or 0) if row else 0
    pushes = (row["pushes"] or 0) if row else 0
    pending = (row["pending"] or 0) if row else 0
    total = (row["total"] or 0) if row else 0

    denominator = wins + losses
    win_rate = round((wins / denominator) * 100, 1) if denominator > 0 else 0
    ci = metric_with_ci(wins, denominator, min_sample=MIN_SAMPLES["overall"])

    return {
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "pending": pending,
        "total": total,
        "win_rate": win_rate,
        "win_rate_ci": ci,
    }


# ─── get_team_ats_record ─────────────────────────────────────────────────────

def get_team_ats_record(team_name, sport):
    """
    Queries the predictions ledger for a team's ATS hit/miss record.
    Returns dict with {wins, losses, total, rate} or None if insufficient data.
    """
    try:
        if _use_supabase():
            sb = _get_supabase()
            rows = (
                sb.table("predictions")
                .select("result")
                .eq("lean_team", team_name)
                .eq("sport", sport)
                .in_("result", ["HIT", "MISS"])
                .execute()
                .data
            )
        else:
            conn = _get_sqlite()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT result FROM predictions "
                    "WHERE lean_team = ? AND sport = ? AND result IN ('HIT', 'MISS')",
                    (team_name, sport)
                )
                rows = [dict(row) for row in cur.fetchall()]
                cur.close()
            finally:
                conn.close()

        if len(rows) < MIN_SAMPLES["ats"]:
            return None

        wins = sum(1 for r in rows if r["result"] == "HIT")
        losses = len(rows) - wins
        total_decided = len(rows)
        rate = round((wins / total_decided) * 100, 1) if total_decided > 0 else 0
        ci = metric_with_ci(wins, total_decided, min_sample=MIN_SAMPLES["ats"])

        return {"wins": wins, "losses": losses, "total": total_decided, "rate": rate, "rate_ci": ci}
    except Exception:
        return None


# ─── get_factor_performance ───────────────────────────────────────────────────

def get_factor_performance(sport):
    """
    Returns hit rates by slot type and overall for a sport.
    Used by the feedback loop factor.
    """
    try:
        if _use_supabase():
            sb = _get_supabase()
            rows = (
                sb.table("predictions")
                .select("slot_type,result")
                .eq("sport", sport)
                .in_("result", ["HIT", "MISS"])
                .execute()
                .data
            )
        else:
            conn = _get_sqlite()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT slot_type, result FROM predictions "
                    "WHERE sport = ? AND result IN ('HIT', 'MISS')",
                    (sport,)
                )
                rows = [dict(row) for row in cur.fetchall()]
                cur.close()
            finally:
                conn.close()

        if not rows:
            return None

        by_slot = {}
        total_wins = 0
        total_decided = 0

        for row in rows:
            slot = row.get("slot_type", "unknown") or "unknown"
            if slot not in by_slot:
                by_slot[slot] = {"wins": 0, "total": 0}
            by_slot[slot]["total"] += 1
            total_decided += 1
            if row["result"] == "HIT":
                by_slot[slot]["wins"] += 1
                total_wins += 1

        for slot in by_slot:
            s = by_slot[slot]
            s["rate"] = round((s["wins"] / s["total"]) * 100, 1) if s["total"] > 0 else 0
            s["rate_ci"] = metric_with_ci(s["wins"], s["total"], min_sample=MIN_SAMPLES["slot"])

        overall_rate = round((total_wins / total_decided) * 100, 1) if total_decided > 0 else 0
        overall_ci = metric_with_ci(total_wins, total_decided, min_sample=MIN_SAMPLES["feedback"])

        return {
            "by_slot": by_slot,
            "overall": {"wins": total_wins, "total": total_decided, "rate": overall_rate, "rate_ci": overall_ci},
        }
    except Exception:
        return None


# ─── CLV Computation ─────────────────────────────────────────────────────────

def _compute_clv(line_at_pick, closing_line, lean_team, home_team):
    """
    Positive CLV = you got a better number than the close.
    From lean team's perspective:
      If lean == home: CLV = line_at_pick - closing_line
      If lean == away: CLV = closing_line - line_at_pick
    """
    if line_at_pick is None or closing_line is None:
        return None, None

    if lean_team == home_team:
        clv = round(line_at_pick - closing_line, 1)
    else:
        clv = round(closing_line - line_at_pick, 1)

    clv_direction = 1 if clv > 0 else 0
    return clv, clv_direction


def _normalize_team_name(name):
    """Normalize team name for fuzzy matching between ESPN and Odds API."""
    return name.strip().lower().replace(".", "").replace("'", "")


def _fetch_odds_api_lines(sport):
    """Fetch current spreads from The Odds API for a sport. Returns dict keyed by normalized matchup."""
    if not ODDS_API_KEY:
        return {}
    sport_key = ODDS_API_SPORT_KEYS.get(sport)
    if not sport_key:
        return {}

    try:
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        resp = requests.get(url, params={
            "apiKey": ODDS_API_KEY,
            "regions": "us",
            "markets": "spreads",
            "bookmakers": "fanduel,draftkings",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {}

    lines = {}
    for game in data:
        home = _normalize_team_name(game.get("home_team", ""))
        away = _normalize_team_name(game.get("away_team", ""))
        if not home or not away:
            continue

        # Average home spread across bookmakers
        spreads = []
        for bk in game.get("bookmakers", []):
            for market in bk.get("markets", []):
                if market.get("key") != "spreads":
                    continue
                for outcome in market.get("outcomes", []):
                    if _normalize_team_name(outcome.get("name", "")) == home:
                        try:
                            spreads.append(float(outcome["point"]))
                        except (ValueError, KeyError):
                            pass

        if spreads:
            avg_spread = round(sum(spreads) / len(spreads), 1)
            lines[f"{home}|{away}"] = avg_spread

    return lines


def fetch_closing_lines(sport=None):
    """
    Fetch closing lines for PENDING predictions.
    Primary: Odds API live spreads. Fallback: ESPN get_game_spread.
    Computes CLV for each prediction that gets a closing line.
    """
    from api_client import get_game_spread

    updated = 0
    sports_to_fetch = [sport] if sport else list(ODDS_API_SPORT_KEYS.keys())

    for sp in sports_to_fetch:
        # Fetch odds API lines once per sport
        odds_lines = _fetch_odds_api_lines(sp)

        if _use_supabase():
            sb = _get_supabase()
            query = sb.table("predictions").select("*").eq("result", "PENDING").is_("closing_line", "null").eq("sport", sp)
            rows = query.execute().data
        else:
            conn = _get_sqlite()
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT * FROM predictions WHERE result = 'PENDING' AND closing_line IS NULL AND sport = ?",
                    (sp,)
                )
                rows = [dict(row) for row in cur.fetchall()]
                cur.close()
            finally:
                conn.close()

        # Collect updates, then batch-write to SQLite with a single connection
        updates = []
        for row in rows:
            home_norm = _normalize_team_name(row["home_team"])
            away_norm = _normalize_team_name(row["away_team"])
            matchup_key = f"{home_norm}|{away_norm}"

            closing = odds_lines.get(matchup_key)

            # Fallback: ESPN spread
            if closing is None:
                try:
                    _, espn_current = get_game_spread(row["event_id"], sp)
                    if espn_current is not None:
                        closing = espn_current
                except Exception:
                    pass

            if closing is None:
                continue

            line_at_pick = row.get("line_at_pick") or row.get("current_spread")
            clv, clv_dir = _compute_clv(line_at_pick, closing, row.get("lean_team"), row["home_team"])

            if _use_supabase():
                sb = _get_supabase()
                update_data = {"closing_line": closing}
                if clv is not None:
                    update_data["clv"] = clv
                    update_data["clv_direction"] = clv_dir
                sb.table("predictions").update(update_data).eq("id", row["id"]).execute()
            else:
                updates.append((closing, clv, clv_dir, row["id"]))

            updated += 1

        # Batch SQLite updates with a single connection
        if updates and not _use_supabase():
            conn = _get_sqlite()
            try:
                cur = conn.cursor()
                for closing, clv, clv_dir, row_id in updates:
                    cur.execute(
                        "UPDATE predictions SET closing_line = ?, clv = ?, clv_direction = ? WHERE id = ?",
                        (closing, clv, clv_dir, row_id)
                    )
                conn.commit()
                cur.close()
            finally:
                conn.close()

    return {"updated": updated}


def _compute_clv_metrics(predictions):
    """Compute CLV summary metrics from a list of prediction dicts."""
    clv_values = [p["clv"] for p in predictions if p.get("clv") is not None]
    clv_beats = sum(1 for p in predictions if p.get("clv_direction") == 1)
    clv_total = len(clv_values)

    avg_clv = round(sum(clv_values) / clv_total, 2) if clv_total > 0 else None
    clv_hit_rate = round(clv_beats / clv_total * 100, 1) if clv_total > 0 else None

    # By tier
    clv_by_tier = []
    for tier in ["STRONG PLAY", "CONFIDENT", "LEAN"]:
        tier_preds = [p for p in predictions if p.get("recommendation") == tier]
        tier_vals = [p["clv"] for p in tier_preds if p.get("clv") is not None]
        tier_beats = sum(1 for p in tier_preds if p.get("clv_direction") == 1)
        tier_total = len(tier_vals)
        if tier_total > 0:
            clv_by_tier.append({
                "tier": tier,
                "avg_clv": round(sum(tier_vals) / tier_total, 2),
                "clv_hit_rate": round(tier_beats / tier_total * 100, 1),
                "count": tier_total,
            })

    # By sport
    clv_by_sport = []
    sports_seen = set(p.get("sport", "") for p in predictions)
    for sp in sorted(sports_seen):
        if not sp:
            continue
        sp_preds = [p for p in predictions if p.get("sport") == sp]
        sp_vals = [p["clv"] for p in sp_preds if p.get("clv") is not None]
        sp_beats = sum(1 for p in sp_preds if p.get("clv_direction") == 1)
        sp_total = len(sp_vals)
        if sp_total > 0:
            clv_by_sport.append({
                "sport": sp,
                "avg_clv": round(sum(sp_vals) / sp_total, 2),
                "clv_hit_rate": round(sp_beats / sp_total * 100, 1),
                "count": sp_total,
            })

    return {
        "avg_clv": avg_clv,
        "clv_hit_rate": clv_hit_rate,
        "clv_total": clv_total,
        "clv_by_tier": clv_by_tier,
        "clv_by_sport": clv_by_sport,
    }


# ─── Drawdown, Variance & Streak Analytics ────────────────────────────────────

def compute_drawdown_metrics(predictions):
    """
    Walk decided predictions chronologically and compute cumulative P&L
    at -110 odds. Track peak P&L, max drawdown, current drawdown, recovery length.
    """
    decided = [
        p for p in predictions
        if p.get("result") in ("HIT", "MISS")
    ]
    decided.sort(key=lambda p: p.get("created_at", "") or "")

    if not decided:
        return {"max_drawdown": 0, "current_drawdown": 0, "recovery_length": 0, "peak_pnl": 0}

    cumulative = 0
    peak = 0
    max_dd = 0
    bets_since_peak = 0

    for p in decided:
        if p["result"] == "HIT":
            cumulative += 100.0 / 110.0  # Win pays +0.909 units
        else:
            cumulative -= 1.0  # Loss costs 1 unit

        if cumulative > peak:
            peak = cumulative
            bets_since_peak = 0
        else:
            bets_since_peak += 1

        dd = peak - cumulative
        if dd > max_dd:
            max_dd = dd

    return {
        "max_drawdown": round(max_dd, 2),
        "current_drawdown": round(peak - cumulative, 2),
        "recovery_length": bets_since_peak,
        "peak_pnl": round(peak, 2),
    }


def compute_variance_metrics(predictions):
    """
    Compute standard deviation of per-bet returns and CLV-based Sharpe ratio.
    Returns breakdown by sport.
    """
    decided = [p for p in predictions if p.get("result") in ("HIT", "MISS")]
    if not decided:
        return {"std_dev": 0, "sharpe_ratio": 0, "by_sport": {}}

    returns = [100.0 / 110.0 if p["result"] == "HIT" else -1.0 for p in decided]
    n = len(returns)
    mean_ret = sum(returns) / n
    variance = sum((r - mean_ret) ** 2 for r in returns) / n if n > 1 else 0
    std_dev = variance ** 0.5

    # CLV-based Sharpe ratio
    clv_values = [p["clv"] for p in predictions if p.get("clv") is not None]
    sharpe = 0
    if clv_values and len(clv_values) >= 2:
        clv_mean = sum(clv_values) / len(clv_values)
        clv_var = sum((v - clv_mean) ** 2 for v in clv_values) / len(clv_values)
        clv_std = clv_var ** 0.5
        if clv_std > 0:
            sharpe = round(clv_mean / clv_std, 2)

    # By sport
    by_sport = {}
    sports_seen = set(p.get("sport", "") for p in decided if p.get("sport"))
    for sp in sorted(sports_seen):
        sp_decided = [p for p in decided if p.get("sport") == sp]
        sp_returns = [100.0 / 110.0 if p["result"] == "HIT" else -1.0 for p in sp_decided]
        sp_n = len(sp_returns)
        sp_mean = sum(sp_returns) / sp_n
        sp_var = sum((r - sp_mean) ** 2 for r in sp_returns) / sp_n if sp_n > 1 else 0
        by_sport[sp] = {
            "std_dev": round(sp_var ** 0.5, 4),
            "count": sp_n,
        }

    return {
        "std_dev": round(std_dev, 4),
        "sharpe_ratio": sharpe,
        "by_sport": by_sport,
    }


def compute_streak_analysis(predictions):
    """
    Compute max win/loss streaks, current streak, and streak distribution.
    """
    decided = [p for p in predictions if p.get("result") in ("HIT", "MISS")]
    decided.sort(key=lambda p: p.get("created_at", "") or "")

    if not decided:
        return {"max_win": 0, "max_loss": 0, "current": {"type": "none", "count": 0}, "distribution": {}}

    max_win = 0
    max_loss = 0
    current_type = decided[0]["result"]
    current_count = 1
    streak_lengths = {"HIT": [], "MISS": []}

    for i in range(1, len(decided)):
        if decided[i]["result"] == current_type:
            current_count += 1
        else:
            streak_lengths[current_type].append(current_count)
            if current_type == "HIT":
                max_win = max(max_win, current_count)
            else:
                max_loss = max(max_loss, current_count)
            current_type = decided[i]["result"]
            current_count = 1

    # Final streak
    streak_lengths[current_type].append(current_count)
    if current_type == "HIT":
        max_win = max(max_win, current_count)
    else:
        max_loss = max(max_loss, current_count)

    # Distribution histogram: count of streaks by length
    distribution = {}
    for lengths in streak_lengths.values():
        for length in lengths:
            distribution[length] = distribution.get(length, 0) + 1

    # Current streak from most recent
    latest_type = decided[-1]["result"]
    latest_count = 0
    for p in reversed(decided):
        if p["result"] == latest_type:
            latest_count += 1
        else:
            break

    return {
        "max_win": max_win,
        "max_loss": max_loss,
        "current": {"type": latest_type, "count": latest_count},
        "distribution": distribution,
    }


def get_performance_by_period(predictions, period="monthly"):
    """
    Group predictions by month and compute W/L/ROI/CLV per period.
    Returns list of {period_label, wins, losses, win_rate, roi, avg_clv}.
    """
    decided = [p for p in predictions if p.get("result") in ("HIT", "MISS", "PUSH")]

    by_period = {}
    for p in decided:
        date_str = p.get("game_date") or p.get("created_at", "")
        if not date_str:
            continue
        # Extract YYYY-MM for monthly grouping
        period_label = date_str[:7]  # "2025-01"
        if period_label not in by_period:
            by_period[period_label] = {"wins": 0, "losses": 0, "pushes": 0, "clv_values": []}

        if p["result"] == "HIT":
            by_period[period_label]["wins"] += 1
        elif p["result"] == "MISS":
            by_period[period_label]["losses"] += 1
        elif p["result"] == "PUSH":
            by_period[period_label]["pushes"] += 1

        if p.get("clv") is not None:
            by_period[period_label]["clv_values"].append(p["clv"])

    result = []
    for label in sorted(by_period.keys()):
        data = by_period[label]
        w, l = data["wins"], data["losses"]
        total = w + l
        win_rate = round(w / total * 100, 1) if total > 0 else 0
        roi = round((w * (100 / 110) - l) / total * 100, 1) if total > 0 else 0
        avg_clv = round(sum(data["clv_values"]) / len(data["clv_values"]), 2) if data["clv_values"] else None

        result.append({
            "period_label": label,
            "wins": w,
            "losses": l,
            "pushes": data["pushes"],
            "win_rate": win_rate,
            "roi": roi,
            "avg_clv": avg_clv,
        })

    return result


def get_clv_trend(sport=None):
    """
    Compute CLV time-series data: daily averages, rolling windows, and health status.
    Returns daily data (last 60 days), rolling 7/14/30 averages, and health assessment.
    """
    # Fetch predictions with CLV data
    if _use_supabase():
        sb = _get_supabase()
        query = sb.table("predictions").select(
            "game_date,clv,clv_direction"
        ).not_.is_("clv", "null").not_.is_("game_date", "null")
        if sport:
            query = query.eq("sport", sport)
        rows = query.execute().data
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        sql = "SELECT game_date, clv, clv_direction FROM predictions WHERE clv IS NOT NULL AND game_date IS NOT NULL"
        params = []
        if sport:
            sql += " AND sport = ?"
            params.append(sport)
        cur.execute(sql, params)
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()

    if not rows:
        return {
            "daily": [],
            "rolling_7": None,
            "rolling_14": None,
            "rolling_30": None,
            "health": {"status": "neutral", "trend": "flat", "message": "No CLV data available yet"},
        }

    # Group by game_date
    by_date = {}
    for r in rows:
        d = r["game_date"]
        if not d:
            continue
        if d not in by_date:
            by_date[d] = {"clv_sum": 0, "beat_count": 0, "count": 0}
        by_date[d]["clv_sum"] += (r["clv"] or 0)
        by_date[d]["beat_count"] += (1 if r.get("clv_direction") == 1 else 0)
        by_date[d]["count"] += 1

    # Sort by date, limit to last 60 days
    sorted_dates = sorted(by_date.keys(), reverse=True)[:60]
    daily = []
    for d in sorted_dates:
        entry = by_date[d]
        avg = round(entry["clv_sum"] / entry["count"], 2) if entry["count"] > 0 else 0
        beat = round(entry["beat_count"] / entry["count"] * 100, 1) if entry["count"] > 0 else 0
        daily.append({"date": d, "avg_clv": avg, "beat_rate": beat, "count": entry["count"]})

    # Compute rolling windows from most-recent-first daily data
    def _rolling(n):
        window = daily[:n]
        if not window:
            return None
        total_clv = sum(d["avg_clv"] * d["count"] for d in window)
        total_beats = sum(round(d["beat_rate"] / 100 * d["count"]) for d in window)
        total_count = sum(d["count"] for d in window)
        if total_count == 0:
            return None
        return {
            "avg_clv": round(total_clv / total_count, 2),
            "beat_rate": round(total_beats / total_count * 100, 1),
            "count": total_count,
        }

    rolling_7 = _rolling(7)
    rolling_14 = _rolling(14)
    rolling_30 = _rolling(30)

    # Health assessment
    r7_clv = rolling_7["avg_clv"] if rolling_7 else 0
    r30_clv = rolling_30["avg_clv"] if rolling_30 else 0

    if r7_clv > 0.3:
        status = "edge"
    elif r7_clv > 0:
        status = "neutral"
    else:
        status = "declining"

    if r7_clv > r30_clv + 0.2:
        trend = "up"
    elif r7_clv < r30_clv - 0.2:
        trend = "down"
    else:
        trend = "flat"

    if status == "edge":
        message = "Your 7-day CLV (+%.1f) is above your 30-day avg (%s%.1f)" % (
            r7_clv, "+" if r30_clv >= 0 else "", r30_clv)
    elif status == "declining":
        message = "Your 7-day CLV (%.1f) has dipped below zero — monitor for sustained decline" % r7_clv
    else:
        message = "CLV is neutral — picks are close to market consensus"

    health = {"status": status, "trend": trend, "message": message}

    return {
        "daily": daily,
        "rolling_7": rolling_7,
        "rolling_14": rolling_14,
        "rolling_30": rolling_30,
        "health": health,
    }


def get_rolling_clv(sport=None, window=50):
    """
    Compute rolling N-bet CLV average per sport.
    Returns rolling CLV series, CLV vs results correlation, and significance.

    Args:
        sport: filter to a single sport, or None for all
        window: number of bets in the rolling window (default 50)

    Returns:
        dict with rolling_clv list, correlation, and per-sport breakdowns
    """
    if _use_supabase():
        sb = _get_supabase()
        query = sb.table("predictions").select(
            "id,sport,clv,clv_direction,result,game_date"
        ).not_.is_("clv", "null").order("game_date", desc=False)
        if sport:
            query = query.eq("sport", sport)
        rows = query.execute().data
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        sql = ("SELECT id, sport, clv, clv_direction, result, game_date "
               "FROM predictions WHERE clv IS NOT NULL ORDER BY game_date ASC")
        params = []
        if sport:
            sql = ("SELECT id, sport, clv, clv_direction, result, game_date "
                   "FROM predictions WHERE clv IS NOT NULL AND sport = ? "
                   "ORDER BY game_date ASC")
            params.append(sport)
        cur.execute(sql, params)
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()

    if not rows:
        return {"rolling_clv": [], "correlation": None, "by_sport": {}}

    # Compute rolling window averages
    rolling_series = []
    for i in range(window, len(rows) + 1):
        batch = rows[i - window:i]
        avg = sum(r["clv"] for r in batch) / len(batch)
        beat_rate = sum(1 for r in batch if r.get("clv_direction") == 1) / len(batch)
        rolling_series.append({
            "bet_number": i,
            "avg_clv": round(avg, 3),
            "beat_rate": round(beat_rate * 100, 1),
            "date": batch[-1].get("game_date", ""),
        })

    # CLV vs results correlation (positive CLV + negative results = variance)
    clv_vals = [r["clv"] for r in rows if r.get("result") in ("win", "loss")]
    result_vals = [1 if r["result"] == "win" else 0
                   for r in rows if r.get("result") in ("win", "loss")]

    correlation = None
    if len(clv_vals) >= 20:
        try:
            n = len(clv_vals)
            mean_c = sum(clv_vals) / n
            mean_r = sum(result_vals) / n
            cov = sum((c - mean_c) * (r - mean_r) for c, r in zip(clv_vals, result_vals)) / n
            std_c = (sum((c - mean_c) ** 2 for c in clv_vals) / n) ** 0.5
            std_r = (sum((r - mean_r) ** 2 for r in result_vals) / n) ** 0.5
            if std_c > 0 and std_r > 0:
                correlation = round(cov / (std_c * std_r), 3)
        except Exception:
            pass

    # Per-sport rolling CLV
    by_sport = {}
    sports_seen = set(r.get("sport", "") for r in rows)
    for sp in sorted(sports_seen):
        if not sp:
            continue
        sp_rows = [r for r in rows if r.get("sport") == sp]
        if len(sp_rows) < window:
            last_n = sp_rows[-min(len(sp_rows), window):]
            avg = sum(r["clv"] for r in last_n) / len(last_n) if last_n else 0
            by_sport[sp] = {
                "avg_clv": round(avg, 3),
                "count": len(sp_rows),
                "sufficient": False,
            }
        else:
            last_n = sp_rows[-window:]
            avg = sum(r["clv"] for r in last_n) / len(last_n)
            by_sport[sp] = {
                "avg_clv": round(avg, 3),
                "count": len(sp_rows),
                "sufficient": True,
            }

    return {
        "rolling_clv": rolling_series,
        "correlation": correlation,
        "by_sport": by_sport,
        "window": window,
        "total_bets": len(rows),
    }


# ─── PRISM Auto-Tracking ──────────────────────────────────────────────────

def save_prism_predictions(props, event_id, sport):
    """
    Upsert non-PASS PRISM signals into prism_predictions table.
    Called automatically after every PRISM analysis run.
    """
    if not props:
        return {"saved": 0}

    now = datetime.now(timezone.utc).isoformat()

    rows = []
    for p in props:
        if p.get("signal") in ("PASS", "SKIP", None):
            continue
        rows.append({
            "event_id": str(event_id),
            "sport": sport,
            "player_name": p.get("player_name", ""),
            "stat_type": p.get("stat_type", ""),
            "projection": p.get("projection"),
            "line": p.get("line"),
            "line_source": p.get("line_source", "estimated"),
            "edge": p.get("edge"),
            "signal": p.get("signal"),
            "confidence": p.get("confidence"),
            "slot_type": p.get("slot_type", ""),
            "created_at": now,
        })

    if not rows:
        return {"saved": 0}

    if _use_supabase():
        sb = _get_supabase()
        sb.table("prism_predictions").upsert(
            rows, on_conflict="event_id,sport,player_name,stat_type"
        ).execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        for r in rows:
            cur.execute("""
                INSERT INTO prism_predictions
                    (event_id, sport, player_name, stat_type,
                     projection, line, line_source, edge, signal,
                     confidence, slot_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, sport, player_name, stat_type)
                DO UPDATE SET
                    projection = EXCLUDED.projection,
                    line = EXCLUDED.line,
                    line_source = EXCLUDED.line_source,
                    edge = EXCLUDED.edge,
                    signal = EXCLUDED.signal,
                    confidence = EXCLUDED.confidence,
                    slot_type = EXCLUDED.slot_type
            """, (
                r["event_id"], r["sport"], r["player_name"], r["stat_type"],
                r["projection"], r["line"], r["line_source"], r["edge"],
                r["signal"], r["confidence"], r["slot_type"], r["created_at"],
            ))
        conn.commit()
        cur.close()
        conn.close()

    return {"saved": len(rows)}


def grade_prism_predictions(sport=None):
    """
    Grade PENDING PRISM predictions by fetching actual stats.
    NBA only — uses balldontlie game log via api_players.
    """
    graded = 0
    results = {"win": 0, "loss": 0, "push": 0, "not_final": 0}

    if _use_supabase():
        sb = _get_supabase()
        query = sb.table("prism_predictions").select("*").eq("result", "PENDING")
        if sport:
            query = query.eq("sport", sport)
        rows = query.execute().data
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        sql = "SELECT * FROM prism_predictions WHERE result = 'PENDING'"
        params = []
        if sport:
            sql += " AND sport = ?"
            params.append(sport)
        cur.execute(sql, params)
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()

    if not rows:
        return {"graded": 0, **results}

    try:
        from api_players import get_player_game_log
    except ImportError:
        return {"graded": 0, **results, "error": "api_players not available"}

    now = datetime.now(timezone.utc).isoformat()
    stat_map = {"PTS": "pts", "REB": "reb", "AST": "ast"}

    for row in rows:
        if row["sport"] != "nba":
            continue

        stat_key = stat_map.get(row["stat_type"])
        if not stat_key:
            continue

        try:
            logs = get_player_game_log(row["player_name"], count=1, sport=row["sport"])
        except Exception:
            results["not_final"] += 1
            continue

        if not logs:
            results["not_final"] += 1
            continue

        actual = logs[0].get(stat_key)
        if actual is None:
            results["not_final"] += 1
            continue

        line = row["line"]
        signal = (row["signal"] or "").upper()
        is_over = "OVER" in signal

        if actual == line:
            result = "PUSH"
        elif is_over:
            result = "WIN" if actual > line else "LOSS"
        else:
            result = "WIN" if actual < line else "LOSS"

        if _use_supabase():
            sb = _get_supabase()
            sb.table("prism_predictions").update({
                "result": result,
                "actual_value": actual,
                "graded_at": now,
            }).eq("id", row["id"]).execute()
        else:
            conn = _get_sqlite()
            cur = conn.cursor()
            cur.execute(
                "UPDATE prism_predictions SET result = ?, actual_value = ?, graded_at = ? WHERE id = ?",
                (result, actual, now, row["id"])
            )
            conn.commit()
            cur.close()
            conn.close()

        graded += 1
        results[result.lower()] = results.get(result.lower(), 0) + 1

    return {"graded": graded, **results}


def get_prism_dashboard(sport=None):
    """
    PRISM prediction accuracy dashboard with Wilson CI and sample sizes.
    Returns breakdowns by stat_type, line_source, and slot_type.
    """
    if _use_supabase():
        sb = _get_supabase()
        query = sb.table("prism_predictions").select("*").neq("result", "PENDING")
        if sport:
            query = query.eq("sport", sport)
        rows = query.execute().data
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        sql = "SELECT * FROM prism_predictions WHERE result != 'PENDING'"
        params = []
        if sport:
            sql += " AND sport = ?"
            params.append(sport)
        cur.execute(sql, params)
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()

    if not rows:
        return {"total": 0, "by_stat_type": [], "by_line_source": [], "by_slot_type": []}

    decided = [r for r in rows if r["result"] in ("WIN", "LOSS")]
    total_wins = sum(1 for r in decided if r["result"] == "WIN")
    total = len(decided)

    overall = metric_with_ci(total_wins, total, min_sample=30)

    def _breakdown(field):
        groups = {}
        for r in decided:
            key = r.get(field, "unknown") or "unknown"
            if key not in groups:
                groups[key] = {"wins": 0, "total": 0}
            groups[key]["total"] += 1
            if r["result"] == "WIN":
                groups[key]["wins"] += 1
        result = []
        for key, g in groups.items():
            ci = metric_with_ci(g["wins"], g["total"], min_sample=20)
            result.append({"label": key, **ci})
        return result

    return {
        "total": total,
        "overall": overall,
        "by_stat_type": _breakdown("stat_type"),
        "by_line_source": _breakdown("line_source"),
        "by_slot_type": _breakdown("slot_type"),
    }
