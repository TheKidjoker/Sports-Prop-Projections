import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.db")


def get_db():
    """Returns a SQLite connection with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates predictions table if it doesn't exist."""
    conn = get_db()
    conn.execute("""
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
    conn.close()


def save_predictions(games, sport):
    """
    Upserts qualifying games into the predictions table.
    Qualifying: cover_pct >= 68.5, has lean_team + action, not skip.
    """
    conn = get_db()
    now = datetime.now(timezone.utc).isoformat()

    for g in games:
        # Skip non-qualifying games
        if g.get("skip"):
            continue
        if (g.get("cover_pct") or 0) < 68.5:
            continue
        if not g.get("lean_team") or not g.get("action"):
            continue

        conn.execute("""
            INSERT INTO predictions
                (event_id, sport, home_team, away_team, game_time_est,
                 lean_team, action, slot_type, recommendation,
                 confirmation_score, cover_pct, current_spread, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id, sport) DO UPDATE SET
                lean_team = excluded.lean_team,
                action = excluded.action,
                slot_type = excluded.slot_type,
                recommendation = excluded.recommendation,
                confirmation_score = excluded.confirmation_score,
                cover_pct = excluded.cover_pct,
                current_spread = excluded.current_spread
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
    conn.close()


def grade_predictions(sport=None):
    """
    Grades PENDING predictions by fetching final scores from ESPN.

    Returns:
        Dict with graded count and summary.
    """
    from api_client import get_game_final_score

    conn = get_db()

    if sport:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE result = 'PENDING' AND sport = ?",
            (sport,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE result = 'PENDING'"
        ).fetchall()

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
        conn.execute("""
            UPDATE predictions
            SET result = ?, home_score = ?, away_score = ?, graded_at = ?
            WHERE id = ?
        """, (result, home_score, away_score, now, row["id"]))

        graded += 1
        results_summary[result.lower()] = results_summary.get(result.lower(), 0) + 1

    conn.commit()
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
        # Moneyline grading: did the lean team win outright?
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

    # ATS grading
    if spread is None:
        # No spread data, can't grade ATS — treat as moneyline
        if lean_team == home_team:
            return "HIT" if home_score > away_score else "MISS"
        else:
            return "HIT" if away_score > home_score else "MISS"

    # spread is from home team's perspective
    if lean_team == home_team:
        adjusted = home_score + spread
        if adjusted > away_score:
            return "HIT"
        elif adjusted == away_score:
            return "PUSH"
        else:
            return "MISS"
    else:
        # Lean is away team, flip perspective
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

    # Base filter
    sport_filter = ""
    params = []
    if sport:
        sport_filter = " AND sport = ?"
        params = [sport]

    # Overall stats
    overall = _aggregate_stats(conn, sport_filter, params)

    # By sport breakdown
    sports = conn.execute(
        "SELECT DISTINCT sport FROM predictions WHERE 1=1" + sport_filter,
        params
    ).fetchall()
    by_sport = []
    for s in sports:
        stats = _aggregate_stats(conn, " AND sport = ?", [s["sport"]])
        stats["sport"] = s["sport"]
        by_sport.append(stats)

    # By slot breakdown
    slots = conn.execute(
        "SELECT DISTINCT slot_type FROM predictions WHERE slot_type != ''" + sport_filter,
        params
    ).fetchall()
    by_slot = []
    for s in slots:
        slot_params = [s["slot_type"]] + params
        stats = _aggregate_stats(conn, " AND slot_type = ?" + sport_filter, slot_params)
        stats["slot_type"] = s["slot_type"]
        by_slot.append(stats)

    # By recommendation breakdown
    recs = conn.execute(
        "SELECT DISTINCT recommendation FROM predictions WHERE recommendation != ''" + sport_filter,
        params
    ).fetchall()
    by_recommendation = []
    for r in recs:
        rec_params = [r["recommendation"]] + params
        stats = _aggregate_stats(conn, " AND recommendation = ?" + sport_filter, rec_params)
        stats["recommendation"] = r["recommendation"]
        by_recommendation.append(stats)

    # Recent 50
    recent_rows = conn.execute(
        "SELECT * FROM predictions WHERE 1=1" + sport_filter +
        " ORDER BY created_at DESC LIMIT 50",
        params
    ).fetchall()
    recent = [dict(r) for r in recent_rows]

    conn.close()

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_slot": by_slot,
        "by_recommendation": by_recommendation,
        "recent": recent,
    }


def _aggregate_stats(conn, where_extra="", params=None):
    """Helper to aggregate win/loss/push/pending counts."""
    if params is None:
        params = []

    row = conn.execute(
        "SELECT "
        "  SUM(CASE WHEN result = 'HIT' THEN 1 ELSE 0 END) as wins, "
        "  SUM(CASE WHEN result = 'MISS' THEN 1 ELSE 0 END) as losses, "
        "  SUM(CASE WHEN result = 'PUSH' THEN 1 ELSE 0 END) as pushes, "
        "  SUM(CASE WHEN result = 'PENDING' THEN 1 ELSE 0 END) as pending, "
        "  COUNT(*) as total "
        "FROM predictions WHERE 1=1" + where_extra,
        params
    ).fetchone()

    wins = row["wins"] or 0
    losses = row["losses"] or 0
    pushes = row["pushes"] or 0
    pending = row["pending"] or 0
    total = row["total"] or 0

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
