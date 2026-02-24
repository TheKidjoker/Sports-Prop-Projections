import sqlite3
import os
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.db")

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
    conn.commit()
    cur.close()
    conn.close()


def _migrate_add_column(cur, column_name):
    """Adds a column to predictions table if it doesn't already exist (SQLite only)."""
    try:
        cur.execute(f"ALTER TABLE predictions ADD COLUMN {column_name} TEXT")
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
            "created_at": now,
        })

    if not rows_to_save:
        return

    if _use_supabase():
        sb = _get_supabase()
        sb.table("predictions").upsert(
            rows_to_save, on_conflict="event_id,sport"
        ).execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        for row in rows_to_save:
            cur.execute("""
                INSERT INTO predictions
                    (event_id, sport, home_team, away_team, game_date, game_time_est,
                     lean_team, action, slot_type, recommendation,
                     confirmation_score, cover_pct, current_spread, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                row["current_spread"], row["created_at"],
            ))
        conn.commit()
        cur.close()
        conn.close()


# ─── grade_predictions ────────────────────────────────────────────────────────

def grade_predictions(sport=None):
    """
    Grades PENDING predictions by fetching final scores from ESPN.
    Returns dict with graded count and summary.
    """
    from api_client import get_game_final_score

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

def get_dashboard_stats(sport=None):
    """
    Returns aggregated dashboard stats.
    Auto-grades all pending predictions before computing stats.
    """
    try:
        grade_predictions(sport)
    except Exception:
        pass

    if _use_supabase():
        return _dashboard_supabase(sport)
    else:
        return _dashboard_sqlite(sport)


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

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_slot": by_slot,
        "by_recommendation": by_recommendation,
        "recent": recent,
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

    return {
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "pending": pending,
        "total": total,
        "win_rate": win_rate,
    }


def _dashboard_sqlite(sport=None):
    conn = _get_sqlite()
    cur = conn.cursor()

    sport_filter = ""
    params = []
    if sport:
        sport_filter = " AND sport = ?"
        params = [sport]

    overall = _aggregate_stats_sqlite(cur, sport_filter, params)

    # By sport
    cur.execute(
        "SELECT DISTINCT sport FROM predictions WHERE 1=1" + sport_filter,
        params
    )
    sports = [dict(row) for row in cur.fetchall()]
    by_sport = []
    for s in sports:
        stats = _aggregate_stats_sqlite(cur, " AND sport = ?", [s["sport"]])
        stats["sport"] = s["sport"]
        by_sport.append(stats)

    # By slot
    cur.execute(
        "SELECT DISTINCT slot_type FROM predictions WHERE slot_type != ''" + sport_filter,
        params
    )
    slots = [dict(row) for row in cur.fetchall()]
    by_slot = []
    for s in slots:
        slot_params = [s["slot_type"]] + params
        stats = _aggregate_stats_sqlite(cur, " AND slot_type = ?" + sport_filter, slot_params)
        stats["slot_type"] = s["slot_type"]
        by_slot.append(stats)

    # By recommendation
    cur.execute(
        "SELECT DISTINCT recommendation FROM predictions WHERE recommendation != ''" + sport_filter,
        params
    )
    recs = [dict(row) for row in cur.fetchall()]
    by_recommendation = []
    for r in recs:
        rec_params = [r["recommendation"]] + params
        stats = _aggregate_stats_sqlite(cur, " AND recommendation = ?" + sport_filter, rec_params)
        stats["recommendation"] = r["recommendation"]
        by_recommendation.append(stats)

    # Recent
    cur.execute(
        "SELECT * FROM predictions WHERE 1=1" + sport_filter +
        " ORDER BY created_at DESC",
        params
    )
    recent = [dict(row) for row in cur.fetchall()]

    cur.close()
    conn.close()

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_slot": by_slot,
        "by_recommendation": by_recommendation,
        "recent": recent,
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

    return {
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "pending": pending,
        "total": total,
        "win_rate": win_rate,
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
            cur = conn.cursor()
            cur.execute(
                "SELECT result FROM predictions "
                "WHERE lean_team = ? AND sport = ? AND result IN ('HIT', 'MISS')",
                (team_name, sport)
            )
            rows = [dict(row) for row in cur.fetchall()]
            cur.close()
            conn.close()

        if len(rows) < 3:
            return None

        wins = sum(1 for r in rows if r["result"] == "HIT")
        losses = len(rows) - wins
        rate = round((wins / len(rows)) * 100, 1) if rows else 0

        return {"wins": wins, "losses": losses, "total": len(rows), "rate": rate}
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
            cur = conn.cursor()
            cur.execute(
                "SELECT slot_type, result FROM predictions "
                "WHERE sport = ? AND result IN ('HIT', 'MISS')",
                (sport,)
            )
            rows = [dict(row) for row in cur.fetchall()]
            cur.close()
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

        overall_rate = round((total_wins / total_decided) * 100, 1) if total_decided > 0 else 0

        return {
            "by_slot": by_slot,
            "overall": {"wins": total_wins, "total": total_decided, "rate": overall_rate},
        }
    except Exception:
        return None
