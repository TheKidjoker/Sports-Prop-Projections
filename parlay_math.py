"""
Parlay Correlation Math — adjusts parlay odds for correlated legs.

Provides correlation coefficients between stat types within each sport,
computes correlation penalties, and adjusts joint probabilities using
a simplified Gaussian copula approach.
"""

import math
from itertools import combinations

# ─── Correlation Matrix ──────────────────────────────────────────────────────
# Dict mapping (sport, stat_a, stat_b) tuples to correlation coefficients.
# Values are symmetric: (sport, A, B) == (sport, B, A).

CORRELATION_MATRIX = {
    # NBA
    ("nba", "PTS", "AST"): 0.30,
    ("nba", "PTS", "REB"): 0.15,
    ("nba", "REB", "AST"): 0.05,
    ("nba", "PTS", "3PM"): 0.45,
    ("nba", "PTS", "STL"): 0.10,
    ("nba", "AST", "STL"): 0.15,
    ("nba", "REB", "BLK"): 0.20,
    # NHL
    ("nhl", "SOG", "Goals"): 0.40,
    ("nhl", "Goals", "AST"): 0.35,
    ("nhl", "SOG", "AST"): 0.20,
    ("nhl", "Goals", "PTS"): 0.60,
    ("nhl", "AST", "PTS"): 0.55,
    # MLB
    ("mlb", "HITS", "TB"): 0.60,
    ("mlb", "HITS", "RBI"): 0.25,
    ("mlb", "HITS", "RUNS"): 0.30,
    ("mlb", "TB", "RBI"): 0.35,
    ("mlb", "TB", "HR"): 0.50,
    ("mlb", "HR", "RBI"): 0.45,
    ("mlb", "RUNS", "RBI"): 0.20,
    # NFL
    ("nfl", "PASS_YDS", "PASS_TD"): 0.45,
    ("nfl", "RUSH_YDS", "RUSH_TD"): 0.35,
    ("nfl", "REC_YDS", "REC"): 0.40,
    ("nfl", "PASS_YDS", "INT"): 0.10,
}


def get_pairwise_correlation(sport, stat_a, stat_b):
    """
    Look up correlation coefficient between two stat types for a sport.
    Returns 0.0 if the pair is unknown (assumed independent).
    """
    sport = sport.lower()
    key1 = (sport, stat_a.upper(), stat_b.upper())
    key2 = (sport, stat_b.upper(), stat_a.upper())
    return CORRELATION_MATRIX.get(key1, CORRELATION_MATRIX.get(key2, 0.0))


def compute_average_pairwise_correlation(sport, stat_list):
    """
    Compute the average pairwise correlation across all combinations
    of stats in a parlay. Uses itertools.combinations for all pairs.

    Args:
        sport: Sport key (e.g. "nba")
        stat_list: List of stat types in the parlay legs

    Returns:
        Average correlation coefficient (0.0 if < 2 legs)
    """
    if len(stat_list) < 2:
        return 0.0

    pairs = list(combinations(stat_list, 2))
    if not pairs:
        return 0.0

    total_corr = sum(
        get_pairwise_correlation(sport, a, b) for a, b in pairs
    )
    return total_corr / len(pairs)


def adjust_parlay_odds(legs, raw_parlay_odds):
    """
    Apply a correlation penalty to raw parlay odds.

    The penalty reduces expected payout proportional to the average
    correlation among legs. Higher correlation = more redundant information
    = lower true odds.

    Args:
        legs: List of dicts with 'sport' and 'stat_type' keys
        raw_parlay_odds: Raw multiplicative parlay odds (decimal)

    Returns:
        Dict with raw_odds, adjusted_odds, correlation_penalty_pct,
        and list of correlated_pairs.
    """
    if not legs or raw_parlay_odds <= 0:
        return {
            "raw_odds": raw_parlay_odds,
            "adjusted_odds": raw_parlay_odds,
            "correlation_penalty_pct": 0,
            "correlated_pairs": [],
        }

    # Group legs by sport to compute within-sport correlations
    by_sport = {}
    for leg in legs:
        sport = leg.get("sport", "").lower()
        stat = leg.get("stat_type", "").upper()
        if sport not in by_sport:
            by_sport[sport] = []
        by_sport[sport].append(stat)

    # Find all correlated pairs
    correlated_pairs = []
    total_correlation = 0
    total_pairs = 0

    for sport, stats in by_sport.items():
        for a, b in combinations(stats, 2):
            corr = get_pairwise_correlation(sport, a, b)
            total_pairs += 1
            total_correlation += corr
            if corr > 0:
                correlated_pairs.append({
                    "sport": sport,
                    "stat_a": a,
                    "stat_b": b,
                    "correlation": corr,
                })

    avg_correlation = total_correlation / total_pairs if total_pairs > 0 else 0

    # Penalty factor: correlation reduces odds by correlation * 0.5
    # (conservative — full correlation would be 1.0x penalty)
    penalty_factor = 0.5
    penalty = avg_correlation * penalty_factor
    adjusted_odds = raw_parlay_odds * (1 - penalty)

    return {
        "raw_odds": round(raw_parlay_odds, 4),
        "adjusted_odds": round(adjusted_odds, 4),
        "correlation_penalty_pct": round(penalty * 100, 1),
        "correlated_pairs": correlated_pairs,
    }


def compute_correlated_ev(legs, win_probabilities):
    """
    Adjust joint probability using a simplified Gaussian copula.

    For correlated events A and B:
        P(A & B) = P(A)*P(B) + rho * sqrt(P(A)(1-P(A)) * P(B)(1-P(B)))

    This gives a more accurate joint probability than naive multiplication
    when legs are correlated.

    Args:
        legs: List of dicts with 'sport' and 'stat_type' keys
        win_probabilities: List of win probabilities (0-1) matching legs

    Returns:
        Dict with naive_joint_prob, adjusted_joint_prob, and ev_impact_pct
    """
    if len(legs) != len(win_probabilities) or len(legs) < 2:
        naive = 1.0
        for p in win_probabilities:
            naive *= p
        return {
            "naive_joint_prob": round(naive, 6),
            "adjusted_joint_prob": round(naive, 6),
            "ev_impact_pct": 0,
        }

    # Start with pairwise adjustments
    # For multi-leg parlays, we iteratively combine pairs
    adjusted_prob = win_probabilities[0]

    for i in range(1, len(legs)):
        p_a = adjusted_prob
        p_b = win_probabilities[i]

        # Find correlation between current accumulated leg and new leg
        rho = get_pairwise_correlation(
            legs[i].get("sport", ""),
            legs[i - 1].get("stat_type", ""),
            legs[i].get("stat_type", ""),
        )

        # Gaussian copula adjustment
        if rho > 0 and 0 < p_a < 1 and 0 < p_b < 1:
            adjustment = rho * math.sqrt(p_a * (1 - p_a) * p_b * (1 - p_b))
            adjusted_prob = p_a * p_b + adjustment
        else:
            adjusted_prob = p_a * p_b

    naive_joint = 1.0
    for p in win_probabilities:
        naive_joint *= p

    # Clamp adjusted probability
    adjusted_prob = max(0.0, min(1.0, adjusted_prob))

    ev_impact = ((adjusted_prob - naive_joint) / naive_joint * 100) if naive_joint > 0 else 0

    return {
        "naive_joint_prob": round(naive_joint, 6),
        "adjusted_joint_prob": round(adjusted_prob, 6),
        "ev_impact_pct": round(ev_impact, 1),
    }
