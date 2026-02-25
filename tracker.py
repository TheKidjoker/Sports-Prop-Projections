import sqlite3
import os
import requests
from datetime import datetime, timezone
from constants import wilson_interval, metric_with_ci, MIN_SAMPLES

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
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

    clv = _compute_clv_metrics(recent)

    return {
        "overall": overall,
        "by_sport": by_sport,
        "by_slot": by_slot,
        "by_recommendation": by_recommendation,
        "recent": recent,
        "clv": clv,
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
            cur = conn.cursor()
            cur.execute(
                "SELECT result FROM predictions "
                "WHERE lean_team = ? AND sport = ? AND result IN ('HIT', 'MISS')",
                (team_name, sport)
            )
            rows = [dict(row) for row in cur.fetchall()]
            cur.close()
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
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM predictions WHERE result = 'PENDING' AND closing_line IS NULL AND sport = ?",
                (sp,)
            )
            rows = [dict(row) for row in cur.fetchall()]
            cur.close()
            conn.close()

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
                conn = _get_sqlite()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE predictions SET closing_line = ?, clv = ?, clv_direction = ? WHERE id = ?",
                    (closing, clv, clv_dir, row["id"])
                )
                conn.commit()
                cur.close()
                conn.close()

            updated += 1

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
