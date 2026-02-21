import sqlite3
import os
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.db")

# Placeholder style: %s for PostgreSQL, ? for SQLite
_PH = "%s" if DATABASE_URL else "?"


def get_db():
    """Returns a database connection (PostgreSQL or SQLite)."""
    if DATABASE_URL:
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn


def _fetchall_dicts(cursor):
    """Convert cursor results to list of dicts (works for both backends)."""
    if DATABASE_URL:
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    else:
        return [dict(row) for row in cursor.fetchall()]


def _fetchone_dict(cursor):
    """Convert single cursor result to dict (works for both backends)."""
    row = cursor.fetchone()
    if row is None:
        return None
    if DATABASE_URL:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    else:
        return dict(row)


def init_db():
    """Creates predictions table if it doesn't exist."""
    conn = get_db()
    cur = conn.cursor()
    if DATABASE_URL:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY,
                event_id TEXT NOT NULL,
                sport TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
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
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                sport TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
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
    conn.commit()
    cur.close()
    conn.close()


def save_predictions(games, sport):
    """
    Upserts qualifying games into the predictions table.
    Qualifying: cover_pct >= 68.5, has lean_team + action, not skip.
    """
    conn = get_db()
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    ph = _PH

    for g in games:
        if g.get("skip"):
            continue
        if (g.get("cover_pct") or 0) < 68.5:
            continue
        if not g.get("lean_team") or not g.get("action"):
            continue

        cur.execute(f"""
            INSERT INTO predictions
                (event_id, sport, home_team, away_team, game_time_est,
                 lean_team, action, slot_type, recommendation,
                 confirmation_score, cover_pct, current_spread, created_at)
            VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            ON CONFLICT(event_id, sport) DO UPDATE SET
                lean_team = EXCLUDED.lean_team,
                action = EXCLUDED.action,
                slot_type = EXCLUDED.slot_type,
                recommendation = EXCLUDED.recommendation,
                confirmation_score = EXCLUDED.confirmation_score,
                cover_pct = EXCLUDED.cover_pct,
                current_spread = EXCLUDED.current_spread
        """, (
            g.get("event_id"),
            sport,
            g.get("home_team"),
            g.get("away_team"),
            g.get("game_time_est", ""),
            g.get("lean_team"),
            g.get("action"),
            g.get("slot_type", ""),
            g.get("recommendation", ""),
            g.get("confirmation_score", 0),
            g.get("cover_pct", 0),
            g.get("current_spread"),
            now,
        ))

    conn.commit()
    cur.close()
    conn.close()


def grade_predictions(sport=None):
    """
    Grades PENDING predictions by fetching final scores from ESPN.

    Returns:
        Dict with graded count and summary.
    """
    from api_client import get_game_final_score

    conn = get_db()
    cur = conn.cursor()
    ph = _PH

    if sport:
        cur.execute(
            f"SELECT * FROM predictions WHERE result = 'PENDING' AND sport = {ph}",
            (sport,)
        )
    else:
        cur.execute("SELECT * FROM predictions WHERE result = 'PENDING'")

    rows = _fetchall_dicts(cur)

    graded = 0
    results_summary = {"hit": 0, "miss": 0, "push": 0, "not_final": 0}

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
        cur.execute(f"""
            UPDATE predictions
            SET result = {ph}, home_score = {ph}, away_score = {ph}, graded_at = {ph}
            WHERE id = {ph}
        """, (result, home_score, away_score, now, row["id"]))

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


def get_dashboard_stats(sport=None):
    """
    Returns aggregated dashboard stats.

    Returns dict with:
        overall: {wins, losses, pushes, pending, total, win_rate}
        by_sport: [{sport, wins, losses, pushes, win_rate}, ...]
        by_slot: [{slot_type, wins, losses, pushes, win_rate}, ...]
        by_recommendation: [{recommendation, wins, losses, pushes, win_rate}, ...]
        recent: [last 50 predictions as dicts]
    """
    conn = get_db()
    cur = conn.cursor()
    ph = _PH

    sport_filter = ""
    params = []
    if sport:
        sport_filter = f" AND sport = {ph}"
        params = [sport]

    overall = _aggregate_stats(cur, sport_filter, params)

    # By sport breakdown
    cur.execute(
        "SELECT DISTINCT sport FROM predictions WHERE 1=1" + sport_filter,
        params
    )
    sports = _fetchall_dicts(cur)
    by_sport = []
    for s in sports:
        stats = _aggregate_stats(cur, f" AND sport = {ph}", [s["sport"]])
        stats["sport"] = s["sport"]
        by_sport.append(stats)

    # By slot breakdown
    cur.execute(
        "SELECT DISTINCT slot_type FROM predictions WHERE slot_type != ''" + sport_filter,
        params
    )
    slots = _fetchall_dicts(cur)
    by_slot = []
    for s in slots:
        slot_params = [s["slot_type"]] + params
        stats = _aggregate_stats(cur, f" AND slot_type = {ph}" + sport_filter, slot_params)
        stats["slot_type"] = s["slot_type"]
        by_slot.append(stats)

    # By recommendation breakdown
    cur.execute(
        "SELECT DISTINCT recommendation FROM predictions WHERE recommendation != ''" + sport_filter,
        params
    )
    recs = _fetchall_dicts(cur)
    by_recommendation = []
    for r in recs:
        rec_params = [r["recommendation"]] + params
        stats = _aggregate_stats(cur, f" AND recommendation = {ph}" + sport_filter, rec_params)
        stats["recommendation"] = r["recommendation"]
        by_recommendation.append(stats)

    # Recent 50
    cur.execute(
        "SELECT * FROM predictions WHERE 1=1" + sport_filter +
        " ORDER BY created_at DESC LIMIT 50",
        params
    )
    recent = _fetchall_dicts(cur)

    cur.close()
    conn.close()

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_slot": by_slot,
        "by_recommendation": by_recommendation,
        "recent": recent,
    }


def _aggregate_stats(cur, where_extra="", params=None):
    """Helper to aggregate win/loss/push/pending counts."""
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
    row = _fetchone_dict(cur)

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
