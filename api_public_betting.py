# ─── Synthetic Public Betting Estimation ──────────────────────────────────────
# Estimates public betting percentages by comparing consensus line to Pinnacle.
# If consensus is shaded 0.5+ pts from Pinnacle toward a side = public money.
# Free — uses existing odds data, no additional API needed.

import logging

logger = logging.getLogger(__name__)


def estimate_public_side(odds_data, home_team, away_team):
    """
    Estimate which side the public is on by comparing Pinnacle (sharp)
    to consensus (average of all books).

    Logic:
    - Pinnacle is the sharpest book, closest to "true" probability
    - When consensus deviates from Pinnacle, the deviation direction
      indicates where public money is flowing
    - More negative consensus vs Pinnacle = public on home
    - More positive consensus vs Pinnacle = public on away

    Args:
        odds_data: list of game odds from odds API
        home_team: home team name
        away_team: away team name

    Returns:
        dict with:
            public_side: "home" or "away" or None
            public_pct_estimate: estimated public % (55-80 range)
            sharp_side: opposite of public
            confidence: "low"/"medium"/"high"
            pinnacle_spread: Pinnacle's spread
            consensus_spread: average spread
            difference: absolute difference
    """
    if not odds_data:
        return _empty_result()

    # Find the matching game
    game = _find_game(odds_data, home_team, away_team)
    if game is None:
        return _empty_result()

    bookmakers = game.get("bookmakers", [])
    if not bookmakers:
        return _empty_result()

    # Extract Pinnacle spread
    pinnacle_spread = None
    all_spreads = []

    for bm in bookmakers:
        key = bm.get("key", "").lower()
        for market in bm.get("markets", []):
            if market.get("key") != "spreads":
                continue
            outcomes = market.get("outcomes", [])
            for outcome in outcomes:
                if outcome.get("name") == home_team or (
                    not outcome.get("name") and "home" in str(outcome).lower()
                ):
                    spread = outcome.get("point")
                    if spread is not None:
                        all_spreads.append(spread)
                        if key == "pinnacle":
                            pinnacle_spread = spread

    if pinnacle_spread is None or len(all_spreads) < 3:
        return _empty_result()

    # Consensus = average of all books
    consensus_spread = sum(all_spreads) / len(all_spreads)
    diff = consensus_spread - pinnacle_spread

    # Threshold: 0.5+ pts of deviation indicates public money
    if abs(diff) < 0.5:
        return {
            "public_side": None,
            "public_pct_estimate": 50,
            "sharp_side": None,
            "confidence": "low",
            "pinnacle_spread": pinnacle_spread,
            "consensus_spread": round(consensus_spread, 1),
            "difference": round(abs(diff), 1),
        }

    # More negative consensus = public on home (pushing favorite)
    if diff < 0:
        public_side = "home"
        sharp_side = "away"
    else:
        public_side = "away"
        sharp_side = "home"

    # Estimate public percentage from deviation magnitude
    # 0.5 pts = ~55%, 1.0 pts = ~65%, 1.5 pts = ~72%, 2.0+ pts = ~78%
    abs_diff = abs(diff)
    if abs_diff >= 2.0:
        pct = 78
        confidence = "high"
    elif abs_diff >= 1.5:
        pct = 72
        confidence = "high"
    elif abs_diff >= 1.0:
        pct = 65
        confidence = "medium"
    else:
        pct = 55
        confidence = "low"

    return {
        "public_side": public_side,
        "public_pct_estimate": pct,
        "sharp_side": sharp_side,
        "confidence": confidence,
        "pinnacle_spread": pinnacle_spread,
        "consensus_spread": round(consensus_spread, 1),
        "difference": round(abs_diff, 1),
    }


def estimate_public_moneyline(odds_data, home_team, away_team):
    """
    Estimate public side for moneyline market using same Pinnacle vs consensus approach.

    Returns:
        dict similar to estimate_public_side but for moneyline
    """
    if not odds_data:
        return _empty_result()

    game = _find_game(odds_data, home_team, away_team)
    if game is None:
        return _empty_result()

    bookmakers = game.get("bookmakers", [])
    pinnacle_home_odds = None
    all_home_odds = []

    for bm in bookmakers:
        key = bm.get("key", "").lower()
        for market in bm.get("markets", []):
            if market.get("key") != "h2h":
                continue
            outcomes = market.get("outcomes", [])
            for outcome in outcomes:
                if outcome.get("name") == home_team:
                    odds = outcome.get("price")
                    if odds is not None:
                        all_home_odds.append(odds)
                        if key == "pinnacle":
                            pinnacle_home_odds = odds

    if pinnacle_home_odds is None or len(all_home_odds) < 3:
        return _empty_result()

    consensus_home_odds = sum(all_home_odds) / len(all_home_odds)

    # Compare implied probabilities
    from prop_ev_engine import american_to_implied_prob
    pin_prob = american_to_implied_prob(pinnacle_home_odds)
    con_prob = american_to_implied_prob(round(consensus_home_odds))

    if pin_prob is None or con_prob is None:
        return _empty_result()

    diff = con_prob - pin_prob

    if abs(diff) < 0.02:
        return _empty_result()

    public_side = "home" if diff > 0 else "away"
    sharp_side = "away" if diff > 0 else "home"

    abs_diff = abs(diff)
    if abs_diff >= 0.05:
        pct = 72
        confidence = "high"
    elif abs_diff >= 0.03:
        pct = 62
        confidence = "medium"
    else:
        pct = 55
        confidence = "low"

    return {
        "public_side": public_side,
        "public_pct_estimate": pct,
        "sharp_side": sharp_side,
        "confidence": confidence,
        "pinnacle_spread": pinnacle_home_odds,
        "consensus_spread": round(consensus_home_odds),
        "difference": round(abs_diff * 100, 1),
    }


def _find_game(odds_data, home_team, away_team):
    """Find matching game in odds data."""
    for game in odds_data:
        if (game.get("home_team") == home_team and
                game.get("away_team") == away_team):
            return game
    return None


def _empty_result():
    return {
        "public_side": None,
        "public_pct_estimate": 50,
        "sharp_side": None,
        "confidence": "low",
        "pinnacle_spread": None,
        "consensus_spread": None,
        "difference": 0.0,
    }
