"""
Bet Tracker — personal bet slip for admin users.
Tracks which spread bets and PRISM player props were actually placed,
then grades results against actual outcomes.

Uses the same dual Supabase/SQLite persistence pattern as tracker.py.
"""

import sqlite3
import os
from datetime import datetime, timezone
from constants import wilson_interval

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "predictions.db")

TABLE = "tm_tracked_bets"

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

def init_tracked_bets_db():
    """Creates tm_tracked_bets table if it doesn't exist (SQLite only)."""
    if _use_supabase():
        return
    conn = _get_sqlite()
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            bet_type TEXT NOT NULL,
            sport TEXT NOT NULL,
            event_id TEXT NOT NULL,
            game_date TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            lean_team TEXT,
            spread_at_pick REAL,
            action TEXT,
            recommendation TEXT,
            cover_pct REAL,
            slot_type TEXT,
            player_name TEXT,
            stat_type TEXT,
            prop_line REAL,
            prop_direction TEXT,
            projection REAL,
            edge REAL,
            confidence REAL,
            signal TEXT,
            result TEXT DEFAULT 'PENDING',
            actual_value REAL,
            home_score INTEGER,
            away_score INTEGER,
            created_at TEXT NOT NULL,
            graded_at TEXT,
            notes TEXT,
            closing_line REAL,
            clv REAL,
            clv_direction INTEGER,
            kelly_fraction REAL,
            suggested_units REAL,
            UNIQUE(user_email, event_id, bet_type, player_name, stat_type)
        )
    """)
    # Migrate existing tables: add new columns if they don't exist yet
    for col_def in ("closing_line REAL", "clv REAL", "clv_direction INTEGER",
                    "kelly_fraction REAL", "suggested_units REAL",
                    "model_probability REAL", "implied_probability REAL",
                    "over_odds INTEGER", "under_odds INTEGER",
                    "expected_value REAL", "closing_odds INTEGER",
                    "clv_prob_delta REAL"):
        try:
            cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN {col_def}")
        except Exception:
            pass  # Column already exists
    conn.commit()
    cur.close()
    conn.close()


# ─── save_tracked_bets ────────────────────────────────────────────────────────

def save_tracked_bets(bets, user_email):
    """Upsert a list of bet dicts for this user."""
    if not bets:
        return {"saved": 0}

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for b in bets:
        rows.append({
            "user_email": user_email,
            "bet_type": b.get("bet_type", "spread"),
            "sport": b.get("sport", "nba"),
            "event_id": str(b.get("event_id", "")),
            "game_date": b.get("game_date"),
            "home_team": b.get("home_team", ""),
            "away_team": b.get("away_team", ""),
            "lean_team": b.get("lean_team"),
            "spread_at_pick": b.get("spread_at_pick"),
            "action": b.get("action"),
            "recommendation": b.get("recommendation"),
            "cover_pct": b.get("cover_pct"),
            "slot_type": b.get("slot_type"),
            "player_name": b.get("player_name") or "",
            "stat_type": b.get("stat_type") or "",
            "prop_line": b.get("prop_line"),
            "prop_direction": b.get("prop_direction"),
            "projection": b.get("projection"),
            "edge": b.get("edge"),
            "confidence": b.get("confidence"),
            "signal": b.get("signal"),
            "kelly_fraction": b.get("kelly_fraction"),
            "suggested_units": b.get("suggested_units"),
            "model_probability": b.get("model_probability"),
            "implied_probability": b.get("implied_probability"),
            "over_odds": b.get("over_odds"),
            "under_odds": b.get("under_odds"),
            "expected_value": b.get("expected_value"),
            "result": "PENDING",
            "created_at": now,
        })

    if _use_supabase():
        sb = _get_supabase()
        sb.table(TABLE).upsert(
            rows,
            on_conflict="user_email,event_id,bet_type,player_name,stat_type"
        ).execute()
    else:
        conn = _get_sqlite()
        try:
            cur = conn.cursor()
            for r in rows:
                cur.execute(f"""
                    INSERT INTO {TABLE}
                        (user_email, bet_type, sport, event_id, game_date,
                         home_team, away_team, lean_team, spread_at_pick,
                         action, recommendation, cover_pct, slot_type,
                         player_name, stat_type, prop_line, prop_direction,
                         projection, edge, confidence, signal,
                         kelly_fraction, suggested_units,
                         model_probability, implied_probability,
                         over_odds, under_odds, expected_value,
                         result, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_email, event_id, bet_type, player_name, stat_type)
                    DO UPDATE SET
                        spread_at_pick = excluded.spread_at_pick,
                        action = excluded.action,
                        recommendation = excluded.recommendation,
                        cover_pct = excluded.cover_pct,
                        slot_type = excluded.slot_type,
                        prop_line = excluded.prop_line,
                        prop_direction = excluded.prop_direction,
                        projection = excluded.projection,
                        edge = excluded.edge,
                        confidence = excluded.confidence,
                        signal = excluded.signal,
                        kelly_fraction = excluded.kelly_fraction,
                        suggested_units = excluded.suggested_units,
                        model_probability = excluded.model_probability,
                        implied_probability = excluded.implied_probability,
                        over_odds = excluded.over_odds,
                        under_odds = excluded.under_odds,
                        expected_value = excluded.expected_value
                """, (
                    r["user_email"], r["bet_type"], r["sport"], r["event_id"],
                    r["game_date"], r["home_team"], r["away_team"], r["lean_team"],
                    r["spread_at_pick"], r["action"], r["recommendation"],
                    r["cover_pct"], r["slot_type"], r["player_name"],
                    r["stat_type"], r["prop_line"], r["prop_direction"],
                    r["projection"], r["edge"], r["confidence"], r["signal"],
                    r["kelly_fraction"], r["suggested_units"],
                    r["model_probability"], r["implied_probability"],
                    r["over_odds"], r["under_odds"], r["expected_value"],
                    r["result"], r["created_at"],
                ))
            conn.commit()
            cur.close()
        finally:
            conn.close()

    return {"saved": len(rows)}


# ─── get_tracked_bets ─────────────────────────────────────────────────────────

def get_tracked_bets(user_email, sport=None, status=None):
    """Fetch tracked bets with optional filters, sorted by created_at DESC."""
    if _use_supabase():
        sb = _get_supabase()
        q = sb.table(TABLE).select("*").eq("user_email", user_email)
        if sport:
            q = q.eq("sport", sport)
        if status:
            q = q.eq("result", status)
        q = q.order("created_at", desc=True)
        resp = q.execute()
        return resp.data or []
    else:
        conn = _get_sqlite()
        try:
            cur = conn.cursor()
            sql = f"SELECT * FROM {TABLE} WHERE user_email = ?"
            params = [user_email]
            if sport:
                sql += " AND sport = ?"
                params.append(sport)
            if status:
                sql += " AND result = ?"
                params.append(status)
            sql += " ORDER BY created_at DESC"
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        finally:
            conn.close()
        return rows


# ─── grade_tracked_bets ───────────────────────────────────────────────────────

def grade_tracked_bets(user_email):
    """
    Grades all PENDING bets for this user.
    Spread bets: reuses tracker._determine_result() with ESPN final scores.
    Prop bets (NBA only): uses balldontlie game log to get actual stat value.
    """
    from api_client import get_game_final_score
    from tracker import _determine_result

    pending = get_tracked_bets(user_email, status="PENDING")
    if not pending:
        return {"graded": 0, "wins": 0, "losses": 0, "pushes": 0, "not_final": 0}

    now = datetime.now(timezone.utc).isoformat()
    graded = 0
    wins = 0
    losses = 0
    pushes = 0
    not_final = 0

    for bet in pending:
        bet_id = bet["id"]
        event_id = bet["event_id"]
        sport = bet["sport"]
        bet_type = bet["bet_type"]

        home_score, away_score, is_final = get_game_final_score(event_id, sport)
        if not is_final:
            not_final += 1
            continue

        result = None
        actual_value = None

        if bet_type == "spread":
            tracker_result = _determine_result(
                bet["lean_team"], bet["home_team"], bet["away_team"],
                bet["spread_at_pick"], bet["action"],
                home_score, away_score
            )
            result = {"HIT": "WIN", "MISS": "LOSS", "PUSH": "PUSH"}.get(tracker_result, "LOSS")

        elif bet_type == "prop":
            result, actual_value = _grade_prop_bet(bet, event_id, sport)
            if result is None:
                not_final += 1
                continue

        if result:
            _update_bet_result(bet_id, user_email, result, actual_value,
                               home_score, away_score, now)
            graded += 1
            if result == "WIN":
                wins += 1
            elif result == "LOSS":
                losses += 1
            elif result == "PUSH":
                pushes += 1

    return {
        "graded": graded,
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "not_final": not_final,
    }


def _grade_prop_bet(bet, event_id, sport):
    """Grade a prop bet by looking up actual player stats. Returns (result, actual_value) or (None, None)."""
    if sport not in ("nba", "nhl"):
        return None, None

    try:
        from api_players import get_player_game_log
        logs = get_player_game_log(bet["player_name"], count=1, sport=sport)
        if not logs:
            return None, None

        stat_map = {
            # NBA
            "PTS": "pts", "REB": "reb", "AST": "ast",
            # NHL
            "GOALS": "g", "SOG": "sog",
            # Shared (NHL points = pts, NHL assists = ast)
        }
        stat_type = bet["stat_type"] or ""

        # Handle combo stats (e.g. "PTS+REB+AST", "GOALS+AST")
        if "+" in stat_type:
            parts = stat_type.split("+")
            total = 0
            for part in parts:
                key = stat_map.get(part.strip())
                if not key:
                    return None, None
                val = logs[0].get(key)
                if val is None:
                    return None, None
                total += val
            actual = total
        else:
            stat_key = stat_map.get(stat_type)
            if not stat_key:
                return None, None
            actual = logs[0].get(stat_key)
            if actual is None:
                return None, None

        prop_line = bet["prop_line"]
        direction = (bet["prop_direction"] or "").upper()

        if actual == prop_line:
            return "PUSH", actual
        elif direction == "OVER":
            return ("WIN" if actual > prop_line else "LOSS"), actual
        elif direction == "UNDER":
            return ("WIN" if actual < prop_line else "LOSS"), actual
        else:
            return None, actual
    except Exception:
        return None, None


def _update_bet_result(bet_id, user_email, result, actual_value,
                       home_score, away_score, graded_at):
    """Update a single bet's result in the database."""
    if _use_supabase():
        sb = _get_supabase()
        update = {
            "result": result,
            "home_score": home_score,
            "away_score": away_score,
            "graded_at": graded_at,
        }
        if actual_value is not None:
            update["actual_value"] = actual_value
        sb.table(TABLE).update(update).eq("id", bet_id).eq("user_email", user_email).execute()
    else:
        conn = _get_sqlite()
        try:
            cur = conn.cursor()
            cur.execute(f"""
                UPDATE {TABLE}
                SET result = ?, actual_value = ?, home_score = ?, away_score = ?, graded_at = ?
                WHERE id = ? AND user_email = ?
            """, (result, actual_value, home_score, away_score, graded_at, bet_id, user_email))
            conn.commit()
            cur.close()
        finally:
            conn.close()


# ─── get_tracked_dashboard ────────────────────────────────────────────────────

def get_tracked_dashboard(user_email, sport=None, start_date=None, end_date=None):
    """Aggregates bet tracking stats for the dashboard."""
    all_bets = get_tracked_bets(user_email, sport=sport)

    # Apply date filtering if provided
    if start_date or end_date:
        all_bets = _filter_bets_by_date(all_bets, start_date, end_date)

    decided = [b for b in all_bets if b["result"] in ("WIN", "LOSS", "PUSH")]
    pending = [b for b in all_bets if b["result"] == "PENDING"]

    w = sum(1 for b in decided if b["result"] == "WIN")
    l = sum(1 for b in decided if b["result"] == "LOSS")
    p = sum(1 for b in decided if b["result"] == "PUSH")
    total = w + l
    win_rate = round(w / total * 100, 1) if total > 0 else 0
    ci = wilson_interval(w, total) if total > 0 else (0, 0)

    # ROI at -110 odds: win pays +100/110, loss costs -1
    roi = 0
    if total > 0:
        profit = w * (100 / 110) - l
        roi = round(profit / (w + l) * 100, 1)

    # Current streak
    streak = _compute_streak(decided)

    # By bet type
    by_type = _aggregate_by_field(decided, "bet_type")

    # By sport
    by_sport = _aggregate_by_field(decided, "sport")

    # By recommendation (spreads only)
    spread_decided = [b for b in decided if b["bet_type"] == "spread"]
    by_rec = _aggregate_by_field(spread_decided, "recommendation")

    # By stat type (props only)
    prop_decided = [b for b in decided if b["bet_type"] == "prop"]
    by_stat = _aggregate_by_field(prop_decided, "stat_type")

    # CLV metrics (spread bets with CLV data)
    clv_bets = [b for b in all_bets if b.get("bet_type") == "spread" and b.get("clv") is not None]
    clv_total = len(clv_bets)
    avg_clv = round(sum(b["clv"] for b in clv_bets) / clv_total, 2) if clv_total else None
    beat_close = sum(1 for b in clv_bets if b.get("clv_direction") == 1)
    beat_close_rate = round(beat_close / clv_total * 100, 1) if clv_total else None

    # Analytics
    wl_decided = [b for b in decided if b["result"] in ("WIN", "LOSS")]
    drawdown = _compute_drawdown(wl_decided)
    variance = _compute_variance(wl_decided, all_bets)
    streaks = _compute_streak_analysis(decided)
    cumulative_pnl = _compute_cumulative_pnl(wl_decided)
    monthly_breakdown = _compute_monthly_breakdown(all_bets)

    return {
        "overall": {
            "wins": w,
            "losses": l,
            "pushes": p,
            "total": total,
            "pending": len(pending),
            "win_rate": win_rate,
            "win_rate_ci": {"ci_lower": ci[0], "ci_upper": ci[1]},
            "roi": roi,
            "streak": streak,
        },
        "clv": {
            "avg_clv": avg_clv,
            "beat_close_rate": beat_close_rate,
            "clv_total": clv_total,
        },
        "by_type": by_type,
        "by_sport": by_sport,
        "by_recommendation": by_rec,
        "by_stat_type": by_stat,
        "recent": [_bet_to_dict(b) for b in all_bets[:50]],
        "drawdown": drawdown,
        "variance": variance,
        "streaks": streaks,
        "cumulative_pnl": cumulative_pnl,
        "monthly_breakdown": monthly_breakdown,
    }


def get_bets_with_dashboard(user_email, sport=None, status=None, start_date=None, end_date=None):
    """Combined bets list + dashboard in single DB query (saves duplicate round trip)."""
    all_bets = get_tracked_bets(user_email, sport=sport)

    # Apply date filtering for dashboard computation
    dashboard_bets = _filter_bets_by_date(all_bets, start_date, end_date) if (start_date or end_date) else all_bets

    # Build dashboard from dashboard_bets
    decided = [b for b in dashboard_bets if b["result"] in ("WIN", "LOSS", "PUSH")]
    pending = [b for b in dashboard_bets if b["result"] == "PENDING"]

    w = sum(1 for b in decided if b["result"] == "WIN")
    l = sum(1 for b in decided if b["result"] == "LOSS")
    p = sum(1 for b in decided if b["result"] == "PUSH")
    total = w + l
    win_rate = round(w / total * 100, 1) if total > 0 else 0
    ci = wilson_interval(w, total) if total > 0 else (0, 0)

    roi = 0
    if total > 0:
        profit = w * (100 / 110) - l
        roi = round(profit / (w + l) * 100, 1)

    streak = _compute_streak(decided)
    by_type = _aggregate_by_field(decided, "bet_type")
    by_sport = _aggregate_by_field(decided, "sport")
    spread_decided = [b for b in decided if b["bet_type"] == "spread"]
    by_rec = _aggregate_by_field(spread_decided, "recommendation")
    prop_decided = [b for b in decided if b["bet_type"] == "prop"]
    by_stat = _aggregate_by_field(prop_decided, "stat_type")

    clv_bets = [b for b in dashboard_bets if b.get("bet_type") == "spread" and b.get("clv") is not None]
    clv_total = len(clv_bets)
    avg_clv = round(sum(b["clv"] for b in clv_bets) / clv_total, 2) if clv_total else None
    beat_close = sum(1 for b in clv_bets if b.get("clv_direction") == 1)
    beat_close_rate = round(beat_close / clv_total * 100, 1) if clv_total else None

    # Analytics
    wl_decided = [b for b in decided if b["result"] in ("WIN", "LOSS")]
    drawdown = _compute_drawdown(wl_decided)
    variance = _compute_variance(wl_decided, dashboard_bets)
    streaks = _compute_streak_analysis(decided)
    cumulative_pnl = _compute_cumulative_pnl(wl_decided)
    monthly_breakdown = _compute_monthly_breakdown(dashboard_bets)

    dashboard = {
        "overall": {
            "wins": w, "losses": l, "pushes": p, "total": total,
            "pending": len(pending), "win_rate": win_rate,
            "win_rate_ci": {"ci_lower": ci[0], "ci_upper": ci[1]},
            "roi": roi, "streak": streak,
        },
        "clv": {"avg_clv": avg_clv, "beat_close_rate": beat_close_rate, "clv_total": clv_total},
        "by_type": by_type, "by_sport": by_sport,
        "by_recommendation": by_rec, "by_stat_type": by_stat,
        "recent": [_bet_to_dict(b) for b in dashboard_bets[:50]],
        "drawdown": drawdown,
        "variance": variance,
        "streaks": streaks,
        "cumulative_pnl": cumulative_pnl,
        "monthly_breakdown": monthly_breakdown,
    }

    # Apply status filter for the bets list (dashboard uses all bets)
    filtered = [b for b in dashboard_bets if b["result"] == status] if status else dashboard_bets
    return {"bets": filtered, "dashboard": dashboard}


def _filter_bets_by_date(bets, start_date=None, end_date=None):
    """Filter bets by date range using game_date or created_at."""
    if not start_date and not end_date:
        return bets
    filtered = []
    for b in bets:
        date_str = b.get("game_date") or b.get("created_at", "")[:10]
        if not date_str:
            filtered.append(b)
            continue
        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue
        filtered.append(b)
    return filtered


def _compute_streak(decided):
    """Compute current W/L streak from most recent bets."""
    if not decided:
        return {"type": "none", "count": 0}
    # Sort by created_at descending
    sorted_bets = sorted(decided, key=lambda b: b.get("created_at", ""), reverse=True)
    streak_type = sorted_bets[0]["result"]
    if streak_type == "PUSH":
        return {"type": "PUSH", "count": 1}
    count = 0
    for b in sorted_bets:
        if b["result"] == streak_type:
            count += 1
        else:
            break
    return {"type": streak_type, "count": count}


def _compute_drawdown(decided):
    """Compute drawdown metrics from decided bets (chronological)."""
    sorted_bets = sorted(decided, key=lambda b: b.get("created_at", ""))
    if not sorted_bets:
        return {"max_drawdown": 0, "current_drawdown": 0, "recovery_length": 0, "peak_pnl": 0}

    cumulative = 0
    peak = 0
    max_dd = 0
    bets_since_peak = 0

    for b in sorted_bets:
        if b["result"] == "WIN":
            cumulative += 100.0 / 110.0
        elif b["result"] == "LOSS":
            cumulative -= 1.0

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


def _compute_variance(decided, all_bets=None):
    """Compute variance and Sharpe ratio from decided bets."""
    if not decided:
        return {"std_dev": 0, "sharpe_ratio": 0, "by_sport": {}}

    returns = [100.0 / 110.0 if b["result"] == "WIN" else -1.0 for b in decided]
    n = len(returns)
    mean_ret = sum(returns) / n
    variance = sum((r - mean_ret) ** 2 for r in returns) / n if n > 1 else 0
    std_dev = variance ** 0.5

    # CLV-based Sharpe
    clv_bets = all_bets or decided
    clv_values = [b["clv"] for b in clv_bets if b.get("clv") is not None]
    sharpe = 0
    if clv_values and len(clv_values) >= 2:
        clv_mean = sum(clv_values) / len(clv_values)
        clv_var = sum((v - clv_mean) ** 2 for v in clv_values) / len(clv_values)
        clv_std = clv_var ** 0.5
        if clv_std > 0:
            sharpe = round(clv_mean / clv_std, 2)

    # By sport
    by_sport = {}
    for sp in sorted(set(b.get("sport", "") for b in decided if b.get("sport"))):
        sp_decided = [b for b in decided if b.get("sport") == sp]
        sp_returns = [100.0 / 110.0 if b["result"] == "WIN" else -1.0 for b in sp_decided]
        sp_n = len(sp_returns)
        sp_mean = sum(sp_returns) / sp_n
        sp_var = sum((r - sp_mean) ** 2 for r in sp_returns) / sp_n if sp_n > 1 else 0
        by_sport[sp] = {"std_dev": round(sp_var ** 0.5, 4), "count": sp_n}

    return {"std_dev": round(std_dev, 4), "sharpe_ratio": sharpe, "by_sport": by_sport}


def _compute_streak_analysis(decided):
    """Max win/loss streaks, current streak, distribution."""
    sorted_bets = sorted(decided, key=lambda b: b.get("created_at", ""))
    wl = [b for b in sorted_bets if b["result"] in ("WIN", "LOSS")]

    if not wl:
        return {"max_win": 0, "max_loss": 0, "current": {"type": "none", "count": 0}, "distribution": {}}

    max_win = 0
    max_loss = 0
    cur_type = wl[0]["result"]
    cur_count = 1
    streak_lengths = {"WIN": [], "LOSS": []}

    for i in range(1, len(wl)):
        if wl[i]["result"] == cur_type:
            cur_count += 1
        else:
            streak_lengths[cur_type].append(cur_count)
            if cur_type == "WIN":
                max_win = max(max_win, cur_count)
            else:
                max_loss = max(max_loss, cur_count)
            cur_type = wl[i]["result"]
            cur_count = 1

    streak_lengths[cur_type].append(cur_count)
    if cur_type == "WIN":
        max_win = max(max_win, cur_count)
    else:
        max_loss = max(max_loss, cur_count)

    distribution = {}
    for lengths in streak_lengths.values():
        for length in lengths:
            distribution[length] = distribution.get(length, 0) + 1

    latest_type = wl[-1]["result"]
    latest_count = 0
    for b in reversed(wl):
        if b["result"] == latest_type:
            latest_count += 1
        else:
            break

    return {
        "max_win": max_win,
        "max_loss": max_loss,
        "current": {"type": latest_type, "count": latest_count},
        "distribution": distribution,
    }


def _compute_cumulative_pnl(decided):
    """Compute cumulative P&L series for charting. Returns list of {date, pnl}."""
    sorted_bets = sorted(decided, key=lambda b: b.get("created_at", ""))
    series = []
    cumulative = 0
    for b in sorted_bets:
        if b["result"] == "WIN":
            cumulative += 100.0 / 110.0
        elif b["result"] == "LOSS":
            cumulative -= 1.0
        date_str = b.get("game_date") or b.get("created_at", "")[:10]
        series.append({"date": date_str, "pnl": round(cumulative, 2)})
    return series


def _compute_monthly_breakdown(all_bets):
    """Group bets by month, compute W/L/ROI/CLV per period."""
    decided = [b for b in all_bets if b.get("result") in ("WIN", "LOSS", "PUSH")]
    by_period = {}
    for b in decided:
        date_str = b.get("game_date") or b.get("created_at", "")
        if not date_str:
            continue
        period_label = date_str[:7]
        if period_label not in by_period:
            by_period[period_label] = {"wins": 0, "losses": 0, "pushes": 0, "clv_values": []}
        if b["result"] == "WIN":
            by_period[period_label]["wins"] += 1
        elif b["result"] == "LOSS":
            by_period[period_label]["losses"] += 1
        elif b["result"] == "PUSH":
            by_period[period_label]["pushes"] += 1
        if b.get("clv") is not None:
            by_period[period_label]["clv_values"].append(b["clv"])

    result = []
    for label in sorted(by_period.keys()):
        data = by_period[label]
        w, l = data["wins"], data["losses"]
        total = w + l
        win_rate = round(w / total * 100, 1) if total > 0 else 0
        roi = round((w * (100 / 110) - l) / total * 100, 1) if total > 0 else 0
        avg_clv = round(sum(data["clv_values"]) / len(data["clv_values"]), 2) if data["clv_values"] else None
        result.append({
            "period_label": label, "wins": w, "losses": l, "pushes": data["pushes"],
            "win_rate": win_rate, "roi": roi, "avg_clv": avg_clv,
        })
    return result


def _aggregate_by_field(bets, field):
    """Group bets by a field and compute W/L/P/rate for each group."""
    groups = {}
    for b in bets:
        key = b.get(field) or "Unknown"
        if key not in groups:
            groups[key] = {"wins": 0, "losses": 0, "pushes": 0}
        if b["result"] == "WIN":
            groups[key]["wins"] += 1
        elif b["result"] == "LOSS":
            groups[key]["losses"] += 1
        elif b["result"] == "PUSH":
            groups[key]["pushes"] += 1

    result = []
    for key, g in groups.items():
        total = g["wins"] + g["losses"]
        rate = round(g["wins"] / total * 100, 1) if total > 0 else 0
        result.append({
            "label": key,
            "wins": g["wins"],
            "losses": g["losses"],
            "pushes": g["pushes"],
            "total": total,
            "win_rate": rate,
        })
    return result


def _bet_to_dict(b):
    """Normalize a bet row to a plain dict for JSON serialization."""
    if isinstance(b, dict):
        return b
    return dict(b)


# ─── delete_tracked_bet ───────────────────────────────────────────────────────

def delete_tracked_bet(bet_id, user_email):
    """Delete a PENDING bet. Returns True if deleted, False otherwise."""
    if _use_supabase():
        sb = _get_supabase()
        resp = sb.table(TABLE).delete().eq("id", bet_id).eq(
            "user_email", user_email
        ).eq("result", "PENDING").execute()
        return bool(resp.data)
    else:
        conn = _get_sqlite()
        try:
            cur = conn.cursor()
            cur.execute(
                f"DELETE FROM {TABLE} WHERE id = ? AND user_email = ? AND result = 'PENDING'",
                (bet_id, user_email),
            )
            deleted = cur.rowcount > 0
            conn.commit()
            cur.close()
        finally:
            conn.close()
        return deleted


# ─── grade_all_tracked_bets ──────────────────────────────────────────────────

def grade_all_tracked_bets():
    """Grade all PENDING bets for ALL users. Called by daily scan."""
    import logging
    logger = logging.getLogger(__name__)

    # Get distinct user emails with PENDING bets
    if _use_supabase():
        sb = _get_supabase()
        resp = sb.table(TABLE).select("user_email").eq("result", "PENDING").execute()
        emails = list(set(r["user_email"] for r in (resp.data or [])))
    else:
        conn = _get_sqlite()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT DISTINCT user_email FROM {TABLE} WHERE result = 'PENDING'")
            emails = [r[0] for r in cur.fetchall()]
            cur.close()
        finally:
            conn.close()

    total_graded = 0
    total_wins = 0
    total_losses = 0
    total_pushes = 0
    total_not_final = 0

    for email in emails:
        try:
            result = grade_tracked_bets(email)
            total_graded += result.get("graded", 0)
            total_wins += result.get("wins", 0)
            total_losses += result.get("losses", 0)
            total_pushes += result.get("pushes", 0)
            total_not_final += result.get("not_final", 0)
        except Exception as exc:
            logger.warning("[bet_tracker] grade failed for %s: %s", email, exc)

    summary = {
        "graded": total_graded,
        "wins": total_wins,
        "losses": total_losses,
        "pushes": total_pushes,
        "not_final": total_not_final,
        "users_graded": len(emails),
    }
    if total_graded > 0:
        logger.info("[bet_tracker] Auto-graded %d bets for %d users: %dW/%dL/%dP",
                     total_graded, len(emails), total_wins, total_losses, total_pushes)
    return summary


# ─── fetch_closing_lines_for_bets ────────────────────────────────────────────

def fetch_closing_lines_for_bets(sport=None):
    """Fetch closing lines and compute CLV for all PENDING spread bets missing closing_line."""
    import logging
    from tracker import _compute_clv, _fetch_odds_api_lines, _normalize_team_name
    from api_client import get_game_spread

    logger = logging.getLogger(__name__)
    ODDS_SPORT_KEYS = {"nba", "nhl", "nfl", "cfb", "cbb"}
    sports_to_fetch = [sport] if sport else list(ODDS_SPORT_KEYS)
    updated = 0

    for sp in sports_to_fetch:
        # Fetch odds API lines once per sport
        try:
            odds_lines = _fetch_odds_api_lines(sp)
        except Exception:
            odds_lines = {}

        # Get PENDING spread bets without closing_line
        if _use_supabase():
            sb = _get_supabase()
            q = sb.table(TABLE).select("*").eq("result", "PENDING").eq("bet_type", "spread").is_("closing_line", "null").eq("sport", sp)
            rows = q.execute().data or []
        else:
            conn = _get_sqlite()
            try:
                cur = conn.cursor()
                cur.execute(
                    f"SELECT * FROM {TABLE} WHERE result = 'PENDING' AND bet_type = 'spread' AND closing_line IS NULL AND sport = ?",
                    (sp,)
                )
                rows = [dict(r) for r in cur.fetchall()]
                cur.close()
            finally:
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

            line_at_pick = row.get("spread_at_pick")
            clv, clv_dir = _compute_clv(line_at_pick, closing, row.get("lean_team"), row["home_team"])

            _update_bet_clv(row["id"], closing, clv, clv_dir)
            updated += 1

    if updated > 0:
        logger.info("[bet_tracker] CLV updated for %d tracked bets", updated)
    return {"updated": updated}


def _update_bet_clv(bet_id, closing_line, clv, clv_direction):
    """Update a single bet's closing line and CLV data."""
    if _use_supabase():
        sb = _get_supabase()
        update = {"closing_line": closing_line}
        if clv is not None:
            update["clv"] = clv
            update["clv_direction"] = clv_direction
        sb.table(TABLE).update(update).eq("id", bet_id).execute()
    else:
        conn = _get_sqlite()
        try:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE {TABLE} SET closing_line = ?, clv = ?, clv_direction = ? WHERE id = ?",
                (closing_line, clv, clv_direction, bet_id)
            )
            conn.commit()
            cur.close()
        finally:
            conn.close()


def fetch_closing_props_for_bets(sport="nba"):
    """
    Fetch closing prop odds and compute CLV for PENDING prop bets.
    Re-fetches current odds from get_player_props_odds_full() and compares
    to odds at time of bet placement.
    """
    import logging
    from api_odds import get_player_props_odds_full
    from prop_ev_engine import american_to_implied_prob

    logger = logging.getLogger(__name__)

    # Fetch current odds
    try:
        current_odds = get_player_props_odds_full(sport)
    except Exception:
        current_odds = {}

    if not current_odds:
        return {"updated": 0}

    stat_label_to_key = {
        "PTS": "points", "REB": "rebounds", "AST": "assists",
        "GOALS": "goals", "SOG": "shots_on_goal",
    }

    # Get PENDING prop bets without closing_odds
    if _use_supabase():
        sb = _get_supabase()
        q = (sb.table(TABLE).select("*")
             .eq("result", "PENDING")
             .eq("bet_type", "prop")
             .is_("closing_odds", "null")
             .eq("sport", sport))
        rows = q.execute().data or []
    else:
        conn = _get_sqlite()
        try:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM {TABLE} WHERE result = 'PENDING' AND bet_type = 'prop' "
                f"AND closing_odds IS NULL AND sport = ?",
                (sport,)
            )
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
        finally:
            conn.close()

    updated = 0
    for row in rows:
        player_name = (row.get("player_name") or "").strip().lower()
        stat_type = row.get("stat_type", "")
        odds_key = stat_label_to_key.get(stat_type, stat_type.lower())
        direction = (row.get("prop_direction") or "").upper()

        player_odds = current_odds.get(player_name, {}).get(odds_key, {})
        if not player_odds:
            continue

        # Determine closing odds for the side we bet on
        if direction == "OVER":
            closing = player_odds.get("over_odds")
        elif direction == "UNDER":
            closing = player_odds.get("under_odds")
        else:
            continue

        if closing is None:
            continue

        # CLV: compare bet implied prob to closing implied prob
        bet_odds = row.get("over_odds") if direction == "OVER" else row.get("under_odds")
        clv_prob_delta = None
        if bet_odds is not None:
            bet_implied = american_to_implied_prob(bet_odds)
            closing_implied = american_to_implied_prob(closing)
            if bet_implied and closing_implied:
                clv_prob_delta = round((closing_implied - bet_implied) * 100, 2)

        # Update in DB
        update_data = {"closing_odds": closing}
        if clv_prob_delta is not None:
            update_data["clv_prob_delta"] = clv_prob_delta

        if _use_supabase():
            sb = _get_supabase()
            sb.table(TABLE).update(update_data).eq("id", row["id"]).execute()
        else:
            conn = _get_sqlite()
            try:
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE {TABLE} SET closing_odds = ?, clv_prob_delta = ? WHERE id = ?",
                    (closing, clv_prob_delta, row["id"])
                )
                conn.commit()
                cur.close()
            finally:
                conn.close()

        updated += 1

    if updated > 0:
        logger.info("[bet_tracker] Prop CLV updated for %d tracked bets", updated)
    return {"updated": updated}
