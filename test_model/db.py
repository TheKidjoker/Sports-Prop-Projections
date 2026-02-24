"""
Test Model DB — schema + CRUD for historical games, features, collection
progress, and model runs.  Uses Supabase when env vars are set, SQLite fallback.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "test_model.db"
)

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


# ─── Schema ────────────────────────────────────────────────────────────────

def init_tm_db():
    if _use_supabase():
        return  # Tables already exist in Supabase
    conn = _get_sqlite()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tm_historical_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            game_date TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_team_id TEXT,
            away_team_id TEXT,
            home_rank INTEGER,
            away_rank INTEGER,
            closing_spread REAL,
            opening_spread REAL,
            over_under REAL,
            home_score INTEGER,
            away_score INTEGER,
            home_covered INTEGER,
            game_status TEXT,
            UNIQUE(event_id, sport)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tm_game_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            sport TEXT NOT NULL,
            features_json TEXT NOT NULL,
            cluster_id INTEGER,
            target INTEGER,
            UNIQUE(event_id, sport)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tm_collection_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT NOT NULL,
            date_str TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            games_found INTEGER DEFAULT 0,
            error_msg TEXT,
            UNIQUE(sport, date_str)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tm_model_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sport TEXT NOT NULL,
            run_type TEXT NOT NULL,
            run_date TEXT NOT NULL,
            accuracy REAL,
            roi REAL,
            clv_avg REAL,
            calibration_error REAL,
            total_predictions INTEGER,
            qualified_bets INTEGER,
            feature_importances TEXT,
            model_params TEXT,
            threshold_analysis TEXT,
            predictions_json TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


# ─── CRUD: Historical Games ────────────────────────────────────────────────

def upsert_historical_game(game_dict):
    row = {
        "event_id": game_dict["event_id"],
        "sport": game_dict["sport"],
        "game_date": game_dict["game_date"],
        "home_team": game_dict["home_team"],
        "away_team": game_dict["away_team"],
        "home_team_id": game_dict.get("home_team_id"),
        "away_team_id": game_dict.get("away_team_id"),
        "home_rank": game_dict.get("home_rank"),
        "away_rank": game_dict.get("away_rank"),
        "closing_spread": game_dict.get("closing_spread"),
        "opening_spread": game_dict.get("opening_spread"),
        "over_under": game_dict.get("over_under"),
        "home_score": game_dict.get("home_score"),
        "away_score": game_dict.get("away_score"),
        "home_covered": game_dict.get("home_covered"),
        "game_status": game_dict.get("game_status"),
    }

    if _use_supabase():
        sb = _get_supabase()
        sb.table("tm_historical_games").upsert(
            row, on_conflict="event_id,sport"
        ).execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tm_historical_games
                (event_id, sport, game_date, home_team, away_team,
                 home_team_id, away_team_id, home_rank, away_rank,
                 closing_spread, opening_spread, over_under,
                 home_score, away_score, home_covered, game_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id, sport) DO UPDATE SET
                closing_spread = EXCLUDED.closing_spread,
                opening_spread = EXCLUDED.opening_spread,
                over_under = EXCLUDED.over_under,
                home_score = EXCLUDED.home_score,
                away_score = EXCLUDED.away_score,
                home_covered = EXCLUDED.home_covered,
                game_status = EXCLUDED.game_status
        """, (
            row["event_id"], row["sport"], row["game_date"],
            row["home_team"], row["away_team"],
            row["home_team_id"], row["away_team_id"],
            row["home_rank"], row["away_rank"],
            row["closing_spread"], row["opening_spread"],
            row["over_under"],
            row["home_score"], row["away_score"],
            row["home_covered"], row["game_status"],
        ))
        conn.commit()
        cur.close()
        conn.close()


def _supabase_fetch_all(table, select_cols, filters, order_col=None):
    """Paginate through Supabase to get ALL rows (bypasses 1000-row default)."""
    sb = _get_supabase()
    page_size = 1000
    offset = 0
    all_rows = []
    while True:
        query = sb.table(table).select(select_cols)
        for col, val in filters:
            query = query.eq(col, val)
        if order_col:
            query = query.order(order_col)
        query = query.range(offset, offset + page_size - 1)
        rows = query.execute().data
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return all_rows


def get_historical_games(sport, before_date=None):
    if _use_supabase():
        sb = _get_supabase()
        page_size = 1000
        offset = 0
        all_rows = []
        while True:
            query = sb.table("tm_historical_games").select("*").eq("sport", sport)
            if before_date:
                query = query.lt("game_date", before_date)
            query = query.order("game_date").range(offset, offset + page_size - 1)
            rows = query.execute().data
            all_rows.extend(rows)
            if len(rows) < page_size:
                break
            offset += page_size
        return all_rows
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        if before_date:
            cur.execute(
                "SELECT * FROM tm_historical_games WHERE sport = ? "
                "AND game_date < ? ORDER BY game_date ASC",
                (sport, before_date),
            )
        else:
            cur.execute(
                "SELECT * FROM tm_historical_games WHERE sport = ? "
                "ORDER BY game_date ASC",
                (sport,),
            )
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return rows


def count_historical_games(sport):
    if _use_supabase():
        sb = _get_supabase()
        resp = (
            sb.table("tm_historical_games")
            .select("*", count="exact")
            .eq("sport", sport)
            .execute()
        )
        return resp.count or 0
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) as cnt FROM tm_historical_games WHERE sport = ?",
            (sport,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row)["cnt"] if row else 0


def count_games_with_spreads(sport):
    if _use_supabase():
        sb = _get_supabase()
        resp = (
            sb.table("tm_historical_games")
            .select("*", count="exact")
            .eq("sport", sport)
            .not_.is_("closing_spread", "null")
            .execute()
        )
        return resp.count or 0
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) as cnt FROM tm_historical_games WHERE sport = ? AND closing_spread IS NOT NULL",
            (sport,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row)["cnt"] if row else 0


# ─── CRUD: Game Features ───────────────────────────────────────────────────

def upsert_game_features(event_id, sport, features_dict, cluster_id=None, target=None):
    features_json = json.dumps(features_dict)

    if _use_supabase():
        sb = _get_supabase()
        sb.table("tm_game_features").upsert({
            "event_id": event_id,
            "sport": sport,
            "features_json": features_json,
            "cluster_id": cluster_id,
            "target": target,
        }, on_conflict="event_id,sport").execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tm_game_features (event_id, sport, features_json, cluster_id, target)
            VALUES (?,?,?,?,?)
            ON CONFLICT(event_id, sport) DO UPDATE SET
                features_json = EXCLUDED.features_json,
                cluster_id = EXCLUDED.cluster_id,
                target = EXCLUDED.target
        """, (event_id, sport, features_json, cluster_id, target))
        conn.commit()
        cur.close()
        conn.close()


def get_game_features_for_training(sport, before_date=None):
    if _use_supabase():
        sb = _get_supabase()
        resp = sb.rpc("get_game_features_for_training", {
            "p_sport": sport,
            "p_before_date": before_date,
        }).execute()
        raw_rows = resp.data or []

        result = []
        for row in raw_rows:
            features = json.loads(row["features_json"])
            features["_target"] = row["target"]
            features["_cluster_id"] = row["cluster_id"]
            features["_game_date"] = row["game_date"]
            result.append(features)
        return result
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        if before_date:
            cur.execute(
                "SELECT f.features_json, f.target, f.cluster_id, g.game_date "
                "FROM tm_game_features f "
                "JOIN tm_historical_games g ON f.event_id = g.event_id AND f.sport = g.sport "
                "WHERE f.sport = ? AND g.game_date < ? AND f.target IS NOT NULL "
                "ORDER BY g.game_date ASC",
                (sport, before_date),
            )
        else:
            cur.execute(
                "SELECT f.features_json, f.target, f.cluster_id, g.game_date "
                "FROM tm_game_features f "
                "JOIN tm_historical_games g ON f.event_id = g.event_id AND f.sport = g.sport "
                "WHERE f.sport = ? AND f.target IS NOT NULL "
                "ORDER BY g.game_date ASC",
                (sport,),
            )
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()

        result = []
        for row in rows:
            features = json.loads(row["features_json"])
            features["_target"] = row["target"]
            features["_cluster_id"] = row["cluster_id"]
            features["_game_date"] = row["game_date"]
            result.append(features)
        return result


def count_game_features(sport):
    if _use_supabase():
        sb = _get_supabase()
        resp = (
            sb.table("tm_game_features")
            .select("*", count="exact")
            .eq("sport", sport)
            .not_.is_("target", "null")
            .execute()
        )
        return resp.count or 0
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) as cnt FROM tm_game_features WHERE sport = ? AND target IS NOT NULL",
            (sport,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row)["cnt"] if row else 0


# ─── CRUD: Collection Progress ─────────────────────────────────────────────

def upsert_collection_progress(sport, date_str, status, games_found=0, error_msg=None):
    if _use_supabase():
        sb = _get_supabase()
        sb.table("tm_collection_progress").upsert({
            "sport": sport,
            "date_str": date_str,
            "status": status,
            "games_found": games_found,
            "error_msg": error_msg,
        }, on_conflict="sport,date_str").execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tm_collection_progress (sport, date_str, status, games_found, error_msg)
            VALUES (?,?,?,?,?)
            ON CONFLICT(sport, date_str) DO UPDATE SET
                status = EXCLUDED.status,
                games_found = EXCLUDED.games_found,
                error_msg = EXCLUDED.error_msg
        """, (sport, date_str, status, games_found, error_msg))
        conn.commit()
        cur.close()
        conn.close()


def get_collection_progress(sport):
    if _use_supabase():
        sb = _get_supabase()
        resp = sb.rpc("get_collection_progress_counts", {
            "p_sport": sport,
        }).execute()
        return {row["status"]: row["cnt"] for row in (resp.data or [])}
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(
            "SELECT status, COUNT(*) as cnt FROM tm_collection_progress "
            "WHERE sport = ? GROUP BY status",
            (sport,),
        )
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return {row["status"]: row["cnt"] for row in rows}


def get_done_dates(sport):
    if _use_supabase():
        rows = _supabase_fetch_all(
            "tm_collection_progress", "date_str",
            [("sport", sport), ("status", "DONE")],
        )
        return {row["date_str"] for row in rows}
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(
            "SELECT date_str FROM tm_collection_progress "
            "WHERE sport = ? AND status = 'DONE'",
            (sport,),
        )
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return {row["date_str"] for row in rows}


# ─── CRUD: Model Runs ──────────────────────────────────────────────────────

def save_model_run(run_dict):
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "sport": run_dict["sport"],
        "run_type": run_dict["run_type"],
        "run_date": now,
        "accuracy": run_dict.get("accuracy"),
        "roi": run_dict.get("roi"),
        "clv_avg": run_dict.get("clv_avg"),
        "calibration_error": run_dict.get("calibration_error"),
        "total_predictions": run_dict.get("total_predictions"),
        "qualified_bets": run_dict.get("qualified_bets"),
        "feature_importances": json.dumps(run_dict.get("feature_importances", {})),
        "model_params": json.dumps(run_dict.get("model_params", {})),
        "threshold_analysis": json.dumps(run_dict.get("threshold_analysis", {})),
        "predictions_json": json.dumps(run_dict.get("predictions", [])),
    }

    if _use_supabase():
        sb = _get_supabase()
        sb.table("tm_model_runs").insert(row).execute()
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tm_model_runs
                (sport, run_type, run_date, accuracy, roi, clv_avg,
                 calibration_error, total_predictions, qualified_bets,
                 feature_importances, model_params, threshold_analysis,
                 predictions_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            row["sport"], row["run_type"], row["run_date"],
            row["accuracy"], row["roi"], row["clv_avg"],
            row["calibration_error"], row["total_predictions"],
            row["qualified_bets"], row["feature_importances"],
            row["model_params"], row["threshold_analysis"],
            row["predictions_json"],
        ))
        conn.commit()
        cur.close()
        conn.close()


def get_latest_model_run(sport, run_type="backtest"):
    if _use_supabase():
        sb = _get_supabase()
        rows = (
            sb.table("tm_model_runs")
            .select("*")
            .eq("sport", sport)
            .eq("run_type", run_type)
            .order("run_date", desc=True)
            .limit(1)
            .execute()
            .data
        )
        row = rows[0] if rows else None
    else:
        conn = _get_sqlite()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM tm_model_runs WHERE sport = ? AND run_type = ? "
            "ORDER BY run_date DESC LIMIT 1",
            (sport, run_type),
        )
        fetched = cur.fetchone()
        row = dict(fetched) if fetched else None
        cur.close()
        conn.close()

    if row:
        for key in ("feature_importances", "model_params", "threshold_analysis", "predictions_json"):
            if row.get(key):
                try:
                    row[key] = json.loads(row[key])
                except (json.JSONDecodeError, TypeError):
                    pass
    return row


def get_backtest_metrics(sport):
    return get_latest_model_run(sport, "backtest")
