"""
Pick Curation — admin approval gate for scan results.
Picks go PENDING on scan, then admin approves/rejects before non-admin users see them.
Only approved picks flow into the prediction tracker.

Uses the same dual Supabase/SQLite persistence pattern as bet_tracker.py.
"""

import sqlite3
import os
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.db")

TABLE = "pick_approvals"

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


def _get_sqlite():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─── init ─────────────────────────────────────────────────────────────────────

def init_pick_approvals_db():
    """Creates pick_approvals table if it doesn't exist (SQLite only)."""
    if _use_supabase():
        return
    conn = _get_sqlite()
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            game_date TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            lean_team TEXT,
            action TEXT,
            recommendation TEXT,
            confirmation_score REAL,
            cover_pct REAL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            admin_notes TEXT,
            admin_lean_override TEXT,
            admin_confidence_override REAL,
            reviewed_at TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(event_id, sport, game_date)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


# ─── sync_picks_from_scan ─────────────────────────────────────────────────────

def sync_picks_from_scan(games, sport):
    """
    Upsert qualifying games (has lean_team, not skip) as PENDING.
    Preserves existing APPROVED/REJECTED status on conflict.
    """
    if not games:
        return

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for g in games:
        if g.get("skip") or not g.get("lean_team"):
            continue
        rows.append({
            "event_id": str(g.get("event_id", "")),
            "sport": sport,
            "game_date": g.get("game_date", "")[:10],
            "home_team": g.get("home_team", ""),
            "away_team": g.get("away_team", ""),
            "lean_team": g.get("lean_team"),
            "action": g.get("action"),
            "recommendation": g.get("recommendation"),
            "confirmation_score": g.get("confirmation_score"),
            "cover_pct": g.get("cover_pct"),
            "status": "PENDING",
            "created_at": now,
        })

    if not rows:
        return

    if _use_supabase():
        sb = _get_supabase()
        for r in rows:
            # Upsert: only update score/pct/action, preserve status
            sb.table(TABLE).upsert(
                r,
                on_conflict="event_id,sport,game_date",
                ignore_duplicates=False,
            ).execute()
            # After upsert, restore status if it was already reviewed
            sb.table(TABLE).update({
                "lean_team": r["lean_team"],
                "action": r["action"],
                "recommendation": r["recommendation"],
                "confirmation_score": r["confirmation_score"],
                "cover_pct": r["cover_pct"],
            }).eq("event_id", r["event_id"]).eq(
                "sport", r["sport"]
            ).eq("game_date", r["game_date"]).eq(
                "status", "PENDING"
            ).execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        for r in rows:
            cur.execute(f"""
                INSERT INTO {TABLE}
                    (event_id, sport, game_date, home_team, away_team,
                     lean_team, action, recommendation, confirmation_score,
                     cover_pct, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?)
                ON CONFLICT(event_id, sport, game_date)
                DO UPDATE SET
                    lean_team = excluded.lean_team,
                    action = excluded.action,
                    recommendation = excluded.recommendation,
                    confirmation_score = excluded.confirmation_score,
                    cover_pct = excluded.cover_pct
                WHERE status = 'PENDING'
            """, (
                r["event_id"], r["sport"], r["game_date"],
                r["home_team"], r["away_team"], r["lean_team"],
                r["action"], r["recommendation"],
                r["confirmation_score"], r["cover_pct"],
                r["created_at"],
            ))
        conn.commit()
        cur.close()
        conn.close()


# ─── approve / reject ─────────────────────────────────────────────────────────

def approve_pick(event_id, sport, game_date, notes=None,
                 lean_override=None, confidence_override=None):
    """Set a pick to APPROVED and save it to the prediction tracker."""
    now = datetime.now(timezone.utc).isoformat()

    if _use_supabase():
        sb = _get_supabase()
        update = {
            "status": "APPROVED",
            "reviewed_at": now,
        }
        if notes:
            update["admin_notes"] = notes
        if lean_override:
            update["admin_lean_override"] = lean_override
        if confidence_override is not None:
            update["admin_confidence_override"] = confidence_override
        sb.table(TABLE).update(update).eq(
            "event_id", event_id
        ).eq("sport", sport).eq("game_date", game_date).execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(f"""
            UPDATE {TABLE}
            SET status = 'APPROVED', reviewed_at = ?,
                admin_notes = COALESCE(?, admin_notes),
                admin_lean_override = COALESCE(?, admin_lean_override),
                admin_confidence_override = COALESCE(?, admin_confidence_override)
            WHERE event_id = ? AND sport = ? AND game_date = ?
        """, (now, notes, lean_override, confidence_override,
              event_id, sport, game_date))
        conn.commit()
        cur.close()
        conn.close()

    _save_approved_to_tracker(event_id, sport, game_date)


def reject_pick(event_id, sport, game_date, notes=None):
    """Set a pick to REJECTED."""
    now = datetime.now(timezone.utc).isoformat()

    if _use_supabase():
        sb = _get_supabase()
        update = {"status": "REJECTED", "reviewed_at": now}
        if notes:
            update["admin_notes"] = notes
        sb.table(TABLE).update(update).eq(
            "event_id", event_id
        ).eq("sport", sport).eq("game_date", game_date).execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(f"""
            UPDATE {TABLE}
            SET status = 'REJECTED', reviewed_at = ?,
                admin_notes = COALESCE(?, admin_notes)
            WHERE event_id = ? AND sport = ? AND game_date = ?
        """, (now, notes, event_id, sport, game_date))
        conn.commit()
        cur.close()
        conn.close()


def approve_all_picks(sport, game_date):
    """Batch approve all PENDING picks for a sport+date."""
    now = datetime.now(timezone.utc).isoformat()

    if _use_supabase():
        sb = _get_supabase()
        sb.table(TABLE).update({
            "status": "APPROVED", "reviewed_at": now,
        }).eq("sport", sport).eq("game_date", game_date).eq(
            "status", "PENDING"
        ).execute()
        # Get all approved for tracker save
        resp = sb.table(TABLE).select("*").eq(
            "sport", sport
        ).eq("game_date", game_date).eq("status", "APPROVED").execute()
        for row in (resp.data or []):
            _save_approved_to_tracker(row["event_id"], sport, game_date)
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(f"""
            UPDATE {TABLE}
            SET status = 'APPROVED', reviewed_at = ?
            WHERE sport = ? AND game_date = ? AND status = 'PENDING'
        """, (now, sport, game_date))
        conn.commit()
        # Save all approved to tracker
        cur.execute(f"""
            SELECT event_id FROM {TABLE}
            WHERE sport = ? AND game_date = ? AND status = 'APPROVED'
        """, (sport, game_date))
        for row in cur.fetchall():
            _save_approved_to_tracker(row["event_id"], sport, game_date)
        cur.close()
        conn.close()


# ─── query helpers ─────────────────────────────────────────────────────────────

def get_pending_picks(sport, game_date):
    """Return all picks for a sport+date (for admin review)."""
    if _use_supabase():
        sb = _get_supabase()
        resp = sb.table(TABLE).select("*").eq(
            "sport", sport
        ).eq("game_date", game_date).order("created_at").execute()
        return resp.data or []
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM {TABLE}
            WHERE sport = ? AND game_date = ?
            ORDER BY created_at
        """, (sport, game_date))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return rows


def get_approved_event_ids(sport, game_date):
    """Return set of approved event_ids for a sport+date."""
    if _use_supabase():
        sb = _get_supabase()
        resp = sb.table(TABLE).select("event_id").eq(
            "sport", sport
        ).eq("game_date", game_date).eq("status", "APPROVED").execute()
        return {r["event_id"] for r in (resp.data or [])}
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT event_id FROM {TABLE}
            WHERE sport = ? AND game_date = ? AND status = 'APPROVED'
        """, (sport, game_date))
        ids = {row["event_id"] for row in cur.fetchall()}
        cur.close()
        conn.close()
        return ids


def get_approval_map(event_ids, sport, game_date):
    """Return dict of event_id -> {status, admin_notes, overrides} for given event_ids."""
    if not event_ids:
        return {}

    if _use_supabase():
        sb = _get_supabase()
        resp = sb.table(TABLE).select("*").eq(
            "sport", sport
        ).eq("game_date", game_date).in_("event_id", list(event_ids)).execute()
        rows = resp.data or []
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        placeholders = ",".join("?" for _ in event_ids)
        cur.execute(f"""
            SELECT * FROM {TABLE}
            WHERE sport = ? AND game_date = ? AND event_id IN ({placeholders})
        """, (sport, game_date, *event_ids))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()

    result = {}
    for r in rows:
        result[r["event_id"]] = {
            "status": r["status"],
            "admin_notes": r.get("admin_notes"),
            "admin_lean_override": r.get("admin_lean_override"),
            "admin_confidence_override": r.get("admin_confidence_override"),
        }
    return result


def has_admin_reviewed(sport, game_date):
    """True if any picks have been reviewed (APPROVED or REJECTED) for this sport+date."""
    if _use_supabase():
        sb = _get_supabase()
        resp = sb.table(TABLE).select("id", count="exact").eq(
            "sport", sport
        ).eq("game_date", game_date).in_(
            "status", ["APPROVED", "REJECTED"]
        ).execute()
        return (resp.count or 0) > 0
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*) FROM {TABLE}
            WHERE sport = ? AND game_date = ? AND status IN ('APPROVED', 'REJECTED')
        """, (sport, game_date))
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return count > 0


# ─── internal helpers ──────────────────────────────────────────────────────────

def _save_approved_to_tracker(event_id, sport, game_date):
    """Save an approved pick into the prediction tracker."""
    try:
        import tracker
        import scan_cache

        cached, _ = scan_cache.get(sport)
        if not cached:
            return

        for g in cached:
            if str(g.get("event_id", "")) == str(event_id):
                tracker.save_predictions([g], sport)
                return
    except Exception:
        pass
