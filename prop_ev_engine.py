# ─── Prop EV Engine ───────────────────────────────────────────────────────────
# Statistical probability and expected value calculations for player props.
# Pure math — no API calls. Uses z-score / CDF for model probability,
# actual market odds for implied probability, and computes true EV.

import math
from scipy.stats import norm


def compute_player_variance(recent_games, stat_key, max_games=15):
    """
    Compute rolling standard deviation from a player's recent game logs.

    Args:
        recent_games: list of game log dicts (from balldontlie/ESPN)
        stat_key: stat to measure ("pts", "reb", "ast", or combo like "pts+reb+ast")
        max_games: max games to use (default 15)

    Returns:
        dict {std_dev, mean, n_games} or None if <5 games
    """
    if not recent_games:
        return None

    # Combo stats: dispatch to combo variance
    if "+" in stat_key:
        return compute_combo_variance(recent_games, stat_key.split("+"), max_games)

    # Map stat_key to game log field names (balldontlie format + NHL)
    key_map = {
        "pts": "pts",
        "reb": "reb",
        "ast": "ast",
        "points": "pts",
        "rebounds": "reb",
        "assists": "ast",
        "g": "g",
        "goals": "g",
        "sog": "sog",
        "shots_on_goal": "sog",
    }
    field = key_map.get(stat_key, stat_key)

    values = []
    for g in recent_games[:max_games]:
        val = g.get(field)
        if val is not None and isinstance(val, (int, float)):
            values.append(float(val))

    if len(values) < 5:
        return None

    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    std_dev = math.sqrt(variance)

    # Floor std_dev at 1.0 to avoid division by near-zero
    std_dev = max(std_dev, 1.0)

    return {
        "std_dev": round(std_dev, 2),
        "mean": round(mean, 2),
        "n_games": len(values),
    }


def compute_combo_variance(recent_games, stat_keys, max_games=15):
    """
    Compute variance of summed stats per game (e.g. pts+reb+ast).

    Args:
        recent_games: list of game log dicts
        stat_keys: list of stat keys to sum (e.g. ["pts", "reb", "ast"])
        max_games: max games to use

    Returns:
        dict {std_dev, mean, n_games} or None if <5 games with all stats
    """
    if not recent_games or not stat_keys:
        return None

    key_map = {
        "pts": "pts", "reb": "reb", "ast": "ast",
        "points": "pts", "rebounds": "reb", "assists": "ast",
        "g": "g", "goals": "g", "goa": "g",
        "sog": "sog", "shots_on_goal": "sog",
    }
    fields = [key_map.get(k, k) for k in stat_keys]

    # Sum stat values per game, only include games where ALL stats are present
    sums = []
    for g in recent_games[:max_games]:
        vals = []
        for f in fields:
            val = g.get(f)
            if val is None or not isinstance(val, (int, float)):
                break
            vals.append(float(val))
        else:
            sums.append(sum(vals))

    if len(sums) < 5:
        return None

    mean = sum(sums) / len(sums)
    variance = sum((v - mean) ** 2 for v in sums) / len(sums)
    std_dev = math.sqrt(variance)

    # Floor std_dev at 2.0 for combos (higher baseline than individual stats)
    std_dev = max(std_dev, 2.0)

    return {
        "std_dev": round(std_dev, 2),
        "mean": round(mean, 2),
        "n_games": len(sums),
    }


def adjust_variance(base_std, is_b2b=False, minutes_unstable=False,
                    has_injury_boost=False):
    """
    Inflate standard deviation for situational uncertainty.

    Args:
        base_std: base standard deviation from game logs
        is_b2b: player's team on back-to-back
        minutes_unstable: PRISM flagged minutes as volatile
        has_injury_boost: injured teammate boosts usage

    Returns:
        adjusted standard deviation (float)
    """
    if base_std is None:
        return None

    adj = base_std
    if is_b2b:
        adj *= 1.10  # +10% variance
    if minutes_unstable:
        adj *= 1.15  # +15% variance
    if has_injury_boost:
        adj *= 1.20  # +20% variance (usage shift uncertainty)

    return round(adj, 2)


def compute_model_probability(projection, line, adjusted_std):
    """
    Compute model probability using z-score and normal CDF.

    z = (line - projection) / adjusted_std
    P(over) = 1 - CDF(z)  — probability the actual exceeds the line
    P(under) = CDF(z)     — probability the actual falls below the line

    Args:
        projection: PRISM projected value
        line: sportsbook line
        adjusted_std: adjusted standard deviation

    Returns:
        dict {z_score, prob_over, prob_under, direction, model_probability}
        or None if inputs invalid
    """
    if projection is None or line is None or adjusted_std is None:
        return None
    if adjusted_std <= 0:
        return None

    z = (line - projection) / adjusted_std
    prob_over = 1.0 - norm.cdf(z)
    prob_under = norm.cdf(z)

    # Direction: whichever side has higher probability
    if prob_over >= prob_under:
        direction = "OVER"
        model_probability = prob_over
    else:
        direction = "UNDER"
        model_probability = prob_under

    # Cap between 5% and 95%
    model_probability = max(0.05, min(0.95, model_probability))

    return {
        "z_score": round(z, 3),
        "prob_over": round(prob_over, 4),
        "prob_under": round(prob_under, 4),
        "direction": direction,
        "model_probability": round(model_probability, 4),
    }


def american_to_implied_prob(odds):
    """
    Convert American odds to implied probability.
    -110 → 0.5238, +150 → 0.40
    """
    if odds is None:
        return None
    if odds < 0:
        return abs(odds) / (abs(odds) + 100.0)
    elif odds > 0:
        return 100.0 / (odds + 100.0)
    else:
        return 0.5


def american_to_decimal_payout(odds):
    """
    Convert American odds to decimal payout (includes stake).
    -110 → 1.909, +150 → 2.50
    """
    if odds is None:
        return None
    if odds < 0:
        return 1.0 + (100.0 / abs(odds))
    elif odds > 0:
        return 1.0 + (odds / 100.0)
    else:
        return 2.0


def remove_vig(over_odds, under_odds):
    """
    Calculate no-vig (fair) probabilities from a two-way market.

    Args:
        over_odds: American odds for over
        under_odds: American odds for under

    Returns:
        dict {over_fair, under_fair, vig_pct} or None
    """
    if over_odds is None or under_odds is None:
        return None

    imp_over = american_to_implied_prob(over_odds)
    imp_under = american_to_implied_prob(under_odds)

    if imp_over is None or imp_under is None:
        return None

    total = imp_over + imp_under
    if total <= 0:
        return None

    return {
        "over_fair": round(imp_over / total, 4),
        "under_fair": round(imp_under / total, 4),
        "vig_pct": round((total - 1.0) * 100, 2),
    }


def calculate_ev(model_prob, market_odds):
    """
    Calculate expected value of a bet.

    EV = (model_prob * net_payout) - ((1 - model_prob) * stake)
    Assumes $100 stake.

    Args:
        model_prob: our model's probability (0-1)
        market_odds: American odds for the side we're betting

    Returns:
        dict {ev_dollars, ev_pct, edge_pct} or None
    """
    if model_prob is None or market_odds is None:
        return None

    decimal_payout = american_to_decimal_payout(market_odds)
    if decimal_payout is None:
        return None

    implied_prob = american_to_implied_prob(market_odds)
    if implied_prob is None:
        return None

    stake = 100.0
    net_payout = (decimal_payout - 1.0) * stake  # What we win (not including stake back)

    ev_dollars = (model_prob * net_payout) - ((1.0 - model_prob) * stake)
    ev_pct = ev_dollars / stake * 100.0
    edge_pct = (model_prob - implied_prob) * 100.0

    return {
        "ev_dollars": round(ev_dollars, 2),
        "ev_pct": round(ev_pct, 2),
        "edge_pct": round(edge_pct, 2),
    }


def analyze_prop(projection, line, recent_games, stat_key,
                 is_b2b=False, minutes_unstable=False, has_injury_boost=False,
                 over_odds=None, under_odds=None):
    """
    Full prop EV analysis pipeline: variance → probability → EV.

    Args:
        projection: PRISM projected value
        line: sportsbook line
        recent_games: list of game log dicts
        stat_key: "pts", "reb", "ast"
        is_b2b: back-to-back flag
        minutes_unstable: minutes volatility flag
        has_injury_boost: injured teammate usage boost
        over_odds: American odds for over (e.g. -110)
        under_odds: American odds for under (e.g. -110)

    Returns:
        dict with full analysis or None if insufficient data
    """
    if projection is None or line is None:
        return None

    # Step 1: Compute variance
    var_result = compute_player_variance(recent_games, stat_key)
    if var_result is None:
        return None

    base_std = var_result["std_dev"]
    n_games = var_result["n_games"]

    # Step 2: Adjust variance for situation
    adj_std = adjust_variance(base_std, is_b2b, minutes_unstable, has_injury_boost)

    # Step 3: Compute model probability
    prob_result = compute_model_probability(projection, line, adj_std)
    if prob_result is None:
        return None

    direction = prob_result["direction"]
    model_prob = prob_result["model_probability"]

    # Step 4: Market probability (if odds available)
    implied_prob = None
    no_vig = None
    market_odds = None

    has_real_odds = over_odds is not None and under_odds is not None
    if has_real_odds:
        no_vig = remove_vig(over_odds, under_odds)
        if direction == "OVER":
            market_odds = over_odds
            implied_prob = no_vig["over_fair"] if no_vig else american_to_implied_prob(over_odds)
        else:
            market_odds = under_odds
            implied_prob = no_vig["under_fair"] if no_vig else american_to_implied_prob(under_odds)
    else:
        # Fallback: assume -110 both sides
        market_odds = -110
        implied_prob = 0.5238  # -110 breakeven

    # Step 5: Calculate EV
    ev_result = calculate_ev(model_prob, market_odds)

    # Step 6: Classify tier
    edge_pct = (model_prob - implied_prob) * 100 if implied_prob else 0
    ev_pct = ev_result["ev_pct"] if ev_result else 0
    line_source = "odds_api" if has_real_odds else "estimated"
    tier = classify_tier(edge_pct, ev_pct, n_games, line_source)

    return {
        "direction": direction,
        "std_dev": base_std,
        "adjusted_std": adj_std,
        "n_games": n_games,
        "z_score": prob_result["z_score"],
        "prob_over": prob_result["prob_over"],
        "prob_under": prob_result["prob_under"],
        "model_probability": round(model_prob * 100, 1),  # as percentage
        "implied_probability": round(implied_prob * 100, 1) if implied_prob else None,
        "edge_pct": round(edge_pct, 1),
        "over_odds": over_odds,
        "under_odds": under_odds,
        "market_odds": market_odds,
        "ev_dollars": ev_result["ev_dollars"] if ev_result else None,
        "ev_pct": ev_result["ev_pct"] if ev_result else None,
        "tier": tier,
        "has_real_odds": has_real_odds,
        "vig_pct": no_vig["vig_pct"] if no_vig else None,
    }


def classify_tier(edge_pct, ev_pct, n_games, line_source="estimated"):
    """
    Classify prop bet tier based on edge magnitude and data quality.

    Tiers:
        STRONG  — high edge + sufficient data + real odds
        CONFIDENT — moderate edge
        LEAN    — marginal edge
        PASS    — not enough edge or data

    Args:
        edge_pct: model_prob - implied_prob (in percentage points)
        ev_pct: expected value percentage
        n_games: number of games in variance sample
        line_source: "odds_api" or "estimated"
    """
    # Insufficient data → cap at LEAN
    max_tier = "STRONG"
    if n_games < 8:
        max_tier = "LEAN"
    elif n_games < 12:
        max_tier = "CONFIDENT"

    # Estimated lines → cap at CONFIDENT
    if line_source == "estimated":
        if max_tier == "STRONG":
            max_tier = "CONFIDENT"

    # Classify by edge
    if edge_pct >= 8.0 and ev_pct >= 5.0:
        tier = "STRONG"
    elif edge_pct >= 5.0 and ev_pct >= 2.0:
        tier = "CONFIDENT"
    elif edge_pct >= 2.0 and ev_pct > 0:
        tier = "LEAN"
    else:
        tier = "PASS"

    # Apply cap
    tier_rank = {"PASS": 0, "LEAN": 1, "CONFIDENT": 2, "STRONG": 3}
    if tier_rank.get(tier, 0) > tier_rank.get(max_tier, 3):
        tier = max_tier

    return tier
