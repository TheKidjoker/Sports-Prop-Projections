"""
Test Model Features — feature engineering with data-leakage prevention.

Historical: processes games chronologically, extracting features from
team_state BEFORE recording each game's result.

Live: converts _analyze_single_game() output to the same feature schema.
"""

import math
from datetime import datetime, timedelta

from time_slots import classify_slot
from line_movement import detect_movement, confirms_slot
from rank_analysis import _detect_rank_scam, _detect_spread_discrepancy
from test_model import db as tm_db
from test_model.date_utils import days_between as _shared_days_between, parse_game_dt

# Feature columns (order matters for model consistency)
FEATURE_COLUMNS = [
    "slot_public", "slot_vegas", "slot_trap",
    "day_of_week",
    "closing_spread", "spread_abs", "is_home_favorite",
    "has_opening_spread", "line_movement", "line_movement_abs", "line_confirms_slot",
    "home_wins_last_7", "away_wins_last_7", "win_diff_last_7",
    "home_scoring_avg_5", "away_scoring_avg_5",
    "home_def_avg_5", "away_def_avg_5",
    "home_rest_days", "away_rest_days",
    "home_b2b", "away_b2b", "rest_advantage",
    "home_rank_filled", "away_rank_filled", "rank_diff",
    "is_rank_scam", "spread_discrepancy",
    "has_h2h", "h2h_margin",
    "has_sentiment", "home_sentiment", "away_sentiment", "sentiment_diff",
    "elo_diff",
    "synthetic_spread_diff", "vig_shading_direction", "market_width",
    "public_side_estimate", "reverse_line_movement",
]

DAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _safe_avg(values, default=0.0):
    if not values:
        return default
    return sum(values) / len(values)


def _days_between(date_str1, date_str2):
    """Days between two ISO date strings (approximate)."""
    return _shared_days_between(date_str1, date_str2, default=3)


def _classify_slot_for_game(game_date_str, sport):
    """Classify slot type from a game date string."""
    tz_dt = parse_game_dt(game_date_str, sport)
    if tz_dt is None:
        return "unknown"
    day = tz_dt.strftime("%A")
    hour, minute = tz_dt.hour, tz_dt.minute
    return classify_slot(day, hour, minute, sport=sport)


def compute_all_features(sport):
    """
    Compute features for ALL historical games of a sport.
    Processes chronologically, maintaining team_state to prevent data leakage.

    Saves computed features to tm_game_features table.
    Returns count of features computed.
    """
    games = tm_db.get_historical_games(sport)
    if not games:
        return 0

    # Team state: {team_name: {results, scores, opp_scores, dates}}
    team_state = {}

    def _get_state(team):
        if team not in team_state:
            team_state[team] = {
                "results": [],     # 1=win, 0=loss
                "scores": [],
                "opp_scores": [],
                "dates": [],
            }
        return team_state[team]

    count = 0
    for game in games:
        # Skip pushes (home_covered == -1) and games without spread
        if game.get("home_covered") is None or game["home_covered"] == -1:
            continue
        if game.get("closing_spread") is None:
            continue

        home = game["home_team"]
        away = game["away_team"]
        home_st = _get_state(home)
        away_st = _get_state(away)

        # ── Extract features BEFORE recording result ──
        features = _extract_features_from_state(game, home_st, away_st, sport)

        target = game["home_covered"]  # 1 = home covered, 0 = did not

        # Save features
        tm_db.upsert_game_features(
            game["event_id"], sport, features,
            cluster_id=None, target=target,
        )
        count += 1

        # ── NOW update team_state with this game's result ──
        home_score = game.get("home_score", 0) or 0
        away_score = game.get("away_score", 0) or 0
        home_won = 1 if home_score > away_score else 0

        home_st["results"].append(home_won)
        home_st["scores"].append(home_score)
        home_st["opp_scores"].append(away_score)
        home_st["dates"].append(game["game_date"])

        away_st["results"].append(1 - home_won)
        away_st["scores"].append(away_score)
        away_st["opp_scores"].append(home_score)
        away_st["dates"].append(game["game_date"])

    return count


def _extract_features_from_state(game, home_st, away_st, sport):
    """Build feature dict from game data + pre-game team state."""
    features = {}
    game_date = game.get("game_date", "")
    closing_spread = game.get("closing_spread")
    opening_spread = game.get("opening_spread")

    # ── Slot features ──
    slot_type = _classify_slot_for_game(game_date, sport)
    features["slot_public"] = 1 if slot_type == "public" else 0
    features["slot_vegas"] = 1 if slot_type in ("vegas", "trap") else 0
    features["slot_trap"] = 1 if slot_type == "trap" else 0

    # ── Day of week ──
    try:
        game_dt = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
        features["day_of_week"] = game_dt.weekday()
    except (ValueError, TypeError, AttributeError):
        features["day_of_week"] = 3

    # ── Spread features ──
    features["closing_spread"] = closing_spread or 0
    features["spread_abs"] = abs(closing_spread) if closing_spread else 0
    features["is_home_favorite"] = 1 if (closing_spread is not None and closing_spread < 0) else 0

    # ── Line movement ──
    if opening_spread is not None and closing_spread is not None:
        features["has_opening_spread"] = 1
        movement_dir, magnitude = detect_movement(opening_spread, closing_spread)
        features["line_movement"] = closing_spread - opening_spread
        features["line_movement_abs"] = magnitude
        features["line_confirms_slot"] = 1 if confirms_slot(movement_dir, slot_type) else 0
    else:
        features["has_opening_spread"] = 0
        features["line_movement"] = 0
        features["line_movement_abs"] = 0
        features["line_confirms_slot"] = 0

    # ── Team form (last 7 results) ──
    home_last7 = home_st["results"][-7:] if home_st["results"] else []
    away_last7 = away_st["results"][-7:] if away_st["results"] else []
    features["home_wins_last_7"] = sum(home_last7)
    features["away_wins_last_7"] = sum(away_last7)
    features["win_diff_last_7"] = features["home_wins_last_7"] - features["away_wins_last_7"]

    # ── Scoring averages (last 5) ──
    features["home_scoring_avg_5"] = _safe_avg(home_st["scores"][-5:])
    features["away_scoring_avg_5"] = _safe_avg(away_st["scores"][-5:])
    features["home_def_avg_5"] = _safe_avg(home_st["opp_scores"][-5:])
    features["away_def_avg_5"] = _safe_avg(away_st["opp_scores"][-5:])

    # ── Rest days ──
    if home_st["dates"]:
        features["home_rest_days"] = min(_days_between(home_st["dates"][-1], game_date), 7)
    else:
        features["home_rest_days"] = 3
    if away_st["dates"]:
        features["away_rest_days"] = min(_days_between(away_st["dates"][-1], game_date), 7)
    else:
        features["away_rest_days"] = 3

    features["home_b2b"] = 1 if features["home_rest_days"] <= 1 else 0
    features["away_b2b"] = 1 if features["away_rest_days"] <= 1 else 0
    features["rest_advantage"] = features["home_rest_days"] - features["away_rest_days"]

    # ── Rank features (CFB/CBB) ──
    home_rank = game.get("home_rank")
    away_rank = game.get("away_rank")
    features["home_rank_filled"] = home_rank if home_rank else 30
    features["away_rank_filled"] = away_rank if away_rank else 30
    features["rank_diff"] = features["home_rank_filled"] - features["away_rank_filled"]

    if sport in ("cfb", "cbb"):
        rank_scam = _detect_rank_scam(home_rank, away_rank, closing_spread, slot_type)
        spread_disc = _detect_spread_discrepancy(home_rank, away_rank, closing_spread, slot_type, sport=sport)
        features["is_rank_scam"] = 1 if rank_scam.get("is_rank_scam") else 0
        features["spread_discrepancy"] = 1 if spread_disc.get("is_discrepancy") else 0
    else:
        features["is_rank_scam"] = 0
        features["spread_discrepancy"] = 0

    # ── H2H (approximated from recent games) ──
    # Check if teams played each other in the team_state history
    h2h_margin = _find_h2h_margin(home_st, away_st, game.get("away_team", ""))
    features["has_h2h"] = 1 if h2h_margin is not None else 0
    features["h2h_margin"] = h2h_margin if h2h_margin is not None else 0

    # ── Sentiment (not available for historical) ──
    features["has_sentiment"] = 0
    features["home_sentiment"] = 0.0
    features["away_sentiment"] = 0.0
    features["sentiment_diff"] = 0.0

    # ── Market maker features (not available for historical) ──
    features["synthetic_spread_diff"] = 0.0
    features["vig_shading_direction"] = 0.0
    features["market_width"] = 0.0
    features["public_side_estimate"] = 0.0
    features["reverse_line_movement"] = 0

    return features


def _find_h2h_margin(home_st, away_st, away_team_name):
    """Check if we have a prior matchup in the state history."""
    # Simple heuristic: not available from state alone for historical.
    # Would require cross-referencing game opponents.
    return None


def compute_live_features(game_analysis, sport, sentiment_data=None):
    """
    Convert a live game analysis dict (from _analyze_single_game or scan_all_games)
    into the same feature schema used by the trained model.

    Args:
        game_analysis: Dict from scan_all_games result
        sport: Sport key
        sentiment_data: Optional {home_sentiment, away_sentiment, sentiment_diff, has_sentiment}

    Returns:
        Dict with same keys as FEATURE_COLUMNS
    """
    features = {}
    slot_type = game_analysis.get("slot_type", "unknown")

    # ── Slot features ──
    features["slot_public"] = 1 if slot_type == "public" else 0
    features["slot_vegas"] = 1 if slot_type in ("vegas", "trap") else 0
    features["slot_trap"] = 1 if slot_type == "trap" else 0

    # ── Day of week ──
    game_date = game_analysis.get("game_date", "")
    try:
        game_dt = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
        features["day_of_week"] = game_dt.weekday()
    except (ValueError, TypeError, AttributeError):
        features["day_of_week"] = datetime.now().weekday()

    # ── Spread features ──
    spread = game_analysis.get("current_spread")
    features["closing_spread"] = spread if spread is not None else 0
    features["spread_abs"] = abs(spread) if spread is not None else 0
    features["is_home_favorite"] = 1 if (spread is not None and spread < 0) else 0

    # ── Line movement (from scan data if available) ──
    lm = game_analysis.get("line_movement", {}) if isinstance(game_analysis.get("line_movement"), dict) else {}
    if lm.get("available"):
        features["has_opening_spread"] = 1
        features["line_movement"] = (lm.get("current_spread", 0) or 0) - (lm.get("opening_spread", 0) or 0)
        features["line_movement_abs"] = lm.get("magnitude", 0) or 0
        features["line_confirms_slot"] = 1 if lm.get("confirms_slot") else 0
    else:
        features["has_opening_spread"] = 0
        features["line_movement"] = 0
        features["line_movement_abs"] = 0
        features["line_confirms_slot"] = 0

    # ── Team form (from live data — we use defaults as we don't have state) ──
    features["home_wins_last_7"] = 3.5
    features["away_wins_last_7"] = 3.5
    features["win_diff_last_7"] = 0

    # ── Scoring averages (defaults) ──
    features["home_scoring_avg_5"] = 100 if sport == "nba" else 25
    features["away_scoring_avg_5"] = 100 if sport == "nba" else 25
    features["home_def_avg_5"] = 100 if sport == "nba" else 25
    features["away_def_avg_5"] = 100 if sport == "nba" else 25

    # ── Rest ──
    b2b = game_analysis.get("b2b", {})
    features["home_rest_days"] = 1 if b2b.get("b2b_penalty") else 2
    features["away_rest_days"] = 1 if b2b.get("b2b_bonus") else 2
    features["home_b2b"] = 1 if b2b.get("b2b_penalty") else 0
    features["away_b2b"] = 1 if b2b.get("b2b_bonus") else 0
    features["rest_advantage"] = features["home_rest_days"] - features["away_rest_days"]

    # ── Rank ──
    home_rank = game_analysis.get("home_rank")
    away_rank = game_analysis.get("away_rank")
    features["home_rank_filled"] = home_rank if home_rank else 30
    features["away_rank_filled"] = away_rank if away_rank else 30
    features["rank_diff"] = features["home_rank_filled"] - features["away_rank_filled"]

    rs = game_analysis.get("rank_scam", {})
    sd = game_analysis.get("spread_discrepancy", {})
    features["is_rank_scam"] = 1 if rs.get("is_rank_scam") else 0
    features["spread_discrepancy"] = 1 if sd.get("is_discrepancy") else 0

    # ── H2H ──
    h2h = game_analysis.get("head_to_head", {})
    features["has_h2h"] = 1 if (h2h.get("h2h_revenge_bonus") or h2h.get("h2h_dominance_bonus")) else 0
    features["h2h_margin"] = 0

    # ── Sentiment ──
    if sentiment_data and sentiment_data.get("has_sentiment"):
        features["has_sentiment"] = 1
        features["home_sentiment"] = sentiment_data.get("home_sentiment", 0)
        features["away_sentiment"] = sentiment_data.get("away_sentiment", 0)
        features["sentiment_diff"] = sentiment_data.get("sentiment_diff", 0)
    else:
        features["has_sentiment"] = 0
        features["home_sentiment"] = 0.0
        features["away_sentiment"] = 0.0
        features["sentiment_diff"] = 0.0

    # ── Market maker features (populated from live scan data) ──
    sm = game_analysis.get("synthetic_market", {})
    features["synthetic_spread_diff"] = sm.get("line_discrepancy", 0.0) or 0.0
    features["vig_shading_direction"] = sm.get("edge", 0.0) or 0.0
    features["market_width"] = 0.0  # Populated when multibook data available

    # Public side estimate from analysis
    pb = game_analysis.get("public_betting", {})
    features["public_side_estimate"] = pb.get("public_pct", 0.0) or 0.0

    # Reverse line movement flag
    features["reverse_line_movement"] = 0
    try:
        from line_movement import detect_reverse_line_movement
        opening = game_analysis.get("opening_spread")
        current = game_analysis.get("current_spread")
        if opening is not None and current is not None:
            spread_dir = "fav" if current < opening else "dog" if current > opening else None
            public_pct = pb.get("public_pct", 50)
            public_side = "fav" if public_pct > 55 else "dog" if public_pct < 45 else None
            if spread_dir and public_side:
                magnitude = abs(current - opening)
                rlm = detect_reverse_line_movement(spread_dir, public_side, magnitude)
                features["reverse_line_movement"] = 1 if rlm.get("is_rlm") else 0
    except Exception:
        pass

    return features


def features_to_array(features_dict):
    """Convert feature dict to ordered list matching FEATURE_COLUMNS."""
    return [features_dict.get(col, 0) for col in FEATURE_COLUMNS]


# ─── Soccer-Specific Feature Engineering ──────────────────────────────────

SOCCER_FEATURE_COLUMNS = [
    "home_xg_regressed", "away_xg_regressed",
    "home_xga_regressed", "away_xga_regressed",
    "elo_diff",
    "home_form_5", "away_form_5",
    "h2h_goals_diff",
    "home_advantage_league",
    "match_importance",
]


def compute_soccer_features(sport="soccer"):
    """
    Compute soccer-specific features for historical matches.
    Uses xG proxies (goals scored/conceded) and Elo ratings.

    Returns count of features computed.
    """
    games = tm_db.get_historical_games(sport)
    if not games:
        return 0

    _LEAGUE_AVG_XG = 1.35
    _PRIOR_WEIGHT = 10

    team_state = {}

    def _get_state(team):
        if team not in team_state:
            team_state[team] = {
                "goals_for": [],
                "goals_against": [],
                "results": [],  # 1=win, 0.5=draw, 0=loss
                "dates": [],
            }
        return team_state[team]

    def _regress(values, prior=_LEAGUE_AVG_XG, weight=_PRIOR_WEIGHT):
        if not values:
            return prior
        avg = sum(values) / len(values)
        n = len(values)
        return (avg * n + prior * weight) / (n + weight)

    count = 0
    for game in games:
        if game.get("game_status") != "STATUS_FINAL":
            continue

        home = game["home_team"]
        away = game["away_team"]
        home_st = _get_state(home)
        away_st = _get_state(away)

        home_score = game.get("home_score", 0) or 0
        away_score = game.get("away_score", 0) or 0

        # Extract features BEFORE recording result
        features = {}
        features["home_xg_regressed"] = round(_regress(home_st["goals_for"]), 3)
        features["away_xg_regressed"] = round(_regress(away_st["goals_for"]), 3)
        features["home_xga_regressed"] = round(_regress(home_st["goals_against"]), 3)
        features["away_xga_regressed"] = round(_regress(away_st["goals_against"]), 3)

        # Elo diff
        try:
            from power_ratings import get_elo_diff
            features["elo_diff"] = get_elo_diff(home, away, "soccer")
        except Exception:
            features["elo_diff"] = 0

        # Form (last 5 results as points: win=3, draw=1, loss=0)
        home_form = home_st["results"][-5:] if home_st["results"] else []
        away_form = away_st["results"][-5:] if away_st["results"] else []
        features["home_form_5"] = sum(3 if r == 1 else (1 if r == 0.5 else 0) for r in home_form)
        features["away_form_5"] = sum(3 if r == 1 else (1 if r == 0.5 else 0) for r in away_form)

        features["h2h_goals_diff"] = 0  # H2H not available from state alone
        features["home_advantage_league"] = 0.45  # Default
        features["match_importance"] = 1.0  # Default

        # Target: 0=home_win, 1=draw, 2=away_win
        if home_score > away_score:
            target = 0
        elif home_score == away_score:
            target = 1
        else:
            target = 2

        tm_db.upsert_game_features(
            game["event_id"], sport, features,
            cluster_id=None, target=target,
        )
        count += 1

        # NOW update team_state
        home_st["goals_for"].append(home_score)
        home_st["goals_against"].append(away_score)
        away_st["goals_for"].append(away_score)
        away_st["goals_against"].append(home_score)

        if home_score > away_score:
            home_st["results"].append(1)
            away_st["results"].append(0)
        elif home_score == away_score:
            home_st["results"].append(0.5)
            away_st["results"].append(0.5)
        else:
            home_st["results"].append(0)
            away_st["results"].append(1)

        home_st["dates"].append(game.get("game_date", ""))
        away_st["dates"].append(game.get("game_date", ""))

    return count


def soccer_features_to_array(features_dict):
    """Convert soccer feature dict to ordered list matching SOCCER_FEATURE_COLUMNS."""
    return [features_dict.get(col, 0) for col in SOCCER_FEATURE_COLUMNS]
