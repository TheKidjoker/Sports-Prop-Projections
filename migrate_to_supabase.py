"""
One-time migration: push all SQLite data to Supabase.

Usage:
    Set SUPABASE_URL and SUPABASE_KEY env vars, then:
    python migrate_to_supabase.py
"""

import os
import sqlite3
import sys

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

PREDICTIONS_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.db")
TEST_MODEL_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_model.db")

BATCH_SIZE = 500


def get_supabase():
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def read_sqlite_table(db_path, table_name):
    """Read all rows from a SQLite table as list of dicts, stripping 'id' column."""
    if not os.path.exists(db_path):
        print(f"  [SKIP] {db_path} not found")
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT * FROM {table_name}")
    except sqlite3.OperationalError as e:
        print(f"  [SKIP] {table_name}: {e}")
        cur.close()
        conn.close()
        return []
    rows = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()

    # Strip auto-generated id column
    for row in rows:
        row.pop("id", None)

    return rows


def push_batch(sb, table_name, rows, use_upsert=False, conflict_cols=None):
    """Push rows to Supabase in batches."""
    total = len(rows)
    pushed = 0

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        if use_upsert and conflict_cols:
            sb.table(table_name).upsert(batch, on_conflict=conflict_cols).execute()
        else:
            sb.table(table_name).insert(batch).execute()
        pushed += len(batch)
        print(f"  {table_name}: {pushed}/{total} rows pushed")


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_KEY environment variables")
        sys.exit(1)

    sb = get_supabase()
    print("Connected to Supabase\n")

    # 1. predictions (from predictions.db)
    print("=== predictions ===")
    rows = read_sqlite_table(PREDICTIONS_DB, "predictions")
    if rows:
        push_batch(sb, "predictions", rows, use_upsert=True, conflict_cols="event_id,sport")
    print()

    # 2. tm_historical_games (from test_model.db)
    print("=== tm_historical_games ===")
    rows = read_sqlite_table(TEST_MODEL_DB, "tm_historical_games")
    if rows:
        push_batch(sb, "tm_historical_games", rows, use_upsert=True, conflict_cols="event_id,sport")
    print()

    # 3. tm_game_features (from test_model.db)
    print("=== tm_game_features ===")
    rows = read_sqlite_table(TEST_MODEL_DB, "tm_game_features")
    if rows:
        push_batch(sb, "tm_game_features", rows, use_upsert=True, conflict_cols="event_id,sport")
    print()

    # 4. tm_collection_progress (from test_model.db)
    print("=== tm_collection_progress ===")
    rows = read_sqlite_table(TEST_MODEL_DB, "tm_collection_progress")
    if rows:
        push_batch(sb, "tm_collection_progress", rows, use_upsert=True, conflict_cols="sport,date_str")
    print()

    # 5. tm_model_runs (from test_model.db) — no unique constraint, use insert
    print("=== tm_model_runs ===")
    rows = read_sqlite_table(TEST_MODEL_DB, "tm_model_runs")
    if rows:
        push_batch(sb, "tm_model_runs", rows, use_upsert=False)
    print()

    print("Migration complete!")


if __name__ == "__main__":
    main()
