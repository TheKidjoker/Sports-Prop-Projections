# ─── Synthetic Market Maker ───────────────────────────────────────────────────
# Generates synthetic lines from Elo ratings and team efficiency data,
# then compares to market to detect inefficiencies.

import math
from constants import POINTS_PER_ELO, STANDARD_OVERROUND
from power_ratings import (
    _expected_score, get_elo, get_elo_diff, get_elo_win_prob, ELO_CONFIG,
)


class SyntheticMarketMaker:
    """
    Generates synthetic spreads, totals, moneylines, and 1X2 markets
    from Elo ratings and team efficiency data.
    """

    # ─── Spread Generation ────────────────────────────────────────────────────

    def generate_spread(self, home, away, sport,
                        home_elo=None, away_elo=None):
        """
        Elo diff -> expected margin via POINTS_PER_ELO -> rounded to standard
        increments -> fair spread + fair probability.

        Args:
            home: home team name
            away: away team name
            sport: sport key
            home_elo: override Elo (if None, looks up from ratings)
            away_elo: override Elo

        Returns:
            dict with fair_spread, fair_prob, home_elo, away_elo
        """
        h_elo = home_elo if home_elo is not None else get_elo(home, sport)
        a_elo = away_elo if away_elo is not None else get_elo(away, sport)

        config = ELO_CONFIG.get(sport, ELO_CONFIG.get("nba", {}))
        home_adv = config.get("home_advantage", 100)

        # Adjusted Elo with home advantage
        h_adj = h_elo + home_adv
        elo_diff = h_adj - a_elo

        # Convert Elo diff to expected margin
        pts_per_elo = POINTS_PER_ELO.get(sport, 28.0)
        expected_margin = elo_diff / pts_per_elo

        # Round to standard 0.5 increments (sportsbook convention)
        fair_spread = round(expected_margin * 2) / 2
        # Negative = home favored (sportsbook convention)
        fair_spread = -fair_spread

        # Fair probability from Elo
        fair_prob = _expected_score(h_adj, a_elo)

        return {
            "fair_spread": fair_spread,
            "fair_prob": round(fair_prob, 4),
            "home_elo": h_elo,
            "away_elo": a_elo,
            "elo_diff": round(elo_diff, 1),
        }

    # ─── Total Generation ─────────────────────────────────────────────────────

    def generate_total(self, home, away, sport,
                       home_off=None, away_off=None,
                       home_def=None, away_def=None,
                       league_avg=None):
        """
        Offensive/defensive efficiency -> expected combined score -> pace-adjusted
        -> fair total + over/under probs.

        Args:
            home_off: home team offensive ppg (or equivalent)
            away_off: away team offensive ppg
            home_def: home team defensive ppg allowed
            away_def: away team defensive ppg allowed
            league_avg: league average ppg per team

        Returns:
            dict with fair_total, over_prob, under_prob
        """
        _LEAGUE_DEFAULTS = {
            "nba": 112.0, "nhl": 3.0, "nfl": 22.0,
            "cbb": 72.0, "mlb": 4.5, "soccer": 1.35,
        }
        avg = league_avg or _LEAGUE_DEFAULTS.get(sport, 100.0)

        h_off = home_off or avg
        a_off = away_off or avg
        h_def = home_def or avg
        a_def = away_def or avg

        # Expected points for each team:
        # home_pts = (home_off + away_def) / 2, adjusted to league average
        home_pts = (h_off * a_def) / avg
        away_pts = (a_off * h_def) / avg

        fair_total = round((home_pts + away_pts) * 2) / 2  # Round to 0.5

        return {
            "fair_total": fair_total,
            "home_pts": round(home_pts, 1),
            "away_pts": round(away_pts, 1),
            "over_prob": 0.50,  # Without historical variance, default to 50/50
            "under_prob": 0.50,
        }

    # ─── Moneyline Generation ─────────────────────────────────────────────────

    def generate_moneyline(self, home, away, sport,
                           home_elo=None, away_elo=None):
        """
        Elo expected_score -> win prob -> apply vig -> American odds.

        Returns:
            dict with home_odds, away_odds, home_prob, away_prob
        """
        h_elo = home_elo if home_elo is not None else get_elo(home, sport)
        a_elo = away_elo if away_elo is not None else get_elo(away, sport)

        config = ELO_CONFIG.get(sport, ELO_CONFIG.get("nba", {}))
        home_adv = config.get("home_advantage", 100)

        home_prob = _expected_score(h_elo + home_adv, a_elo)
        away_prob = 1.0 - home_prob

        # Apply standard overround (vig)
        overround = STANDARD_OVERROUND.get(sport, 0.045)
        home_vigged = home_prob * (1 + overround / 2)
        away_vigged = away_prob * (1 + overround / 2)

        home_odds = _prob_to_american(home_vigged)
        away_odds = _prob_to_american(away_vigged)

        return {
            "home_odds": home_odds,
            "away_odds": away_odds,
            "home_prob": round(home_prob, 4),
            "away_prob": round(away_prob, 4),
        }

    # ─── Soccer 1X2 Generation ────────────────────────────────────────────────

    def generate_1x2(self, home, away, league,
                     home_elo=None, away_elo=None):
        """
        Soccer-specific 3-way market from Elo -> home/draw/away probabilities.

        Uses empirical draw rate relationship: draw_prob increases as teams
        are closer in strength, with baseline ~25% for soccer.

        Returns:
            dict with home_prob, draw_prob, away_prob, home_odds, draw_odds, away_odds
        """
        h_elo = home_elo if home_elo is not None else get_elo(home, "soccer")
        a_elo = away_elo if away_elo is not None else get_elo(away, "soccer")

        config = ELO_CONFIG.get("soccer", ELO_CONFIG.get("nba", {}))
        home_adv = config.get("home_advantage", 80)

        # Two-way probability from Elo
        two_way_home = _expected_score(h_elo + home_adv, a_elo)
        two_way_away = 1.0 - two_way_home

        # Draw probability model: higher when teams are close in strength
        # Base draw rate ~25%, increases when |home_prob - 0.5| is small
        closeness = 1.0 - abs(two_way_home - 0.5) * 2  # 1.0 when equal, 0.0 when dominant
        draw_base = 0.22
        draw_range = 0.12  # Draw ranges from 22% to 34%
        draw_prob = draw_base + draw_range * closeness

        # Distribute remaining probability
        remaining = 1.0 - draw_prob
        home_prob = remaining * two_way_home
        away_prob = remaining * two_way_away

        # Apply vig for odds
        overround = STANDARD_OVERROUND.get("soccer", 0.055)
        vig_mult = 1.0 + overround / 3  # Distribute across 3 outcomes

        return {
            "home_prob": round(home_prob, 4),
            "draw_prob": round(draw_prob, 4),
            "away_prob": round(away_prob, 4),
            "home_odds": _prob_to_american(home_prob * vig_mult),
            "draw_odds": _prob_to_american(draw_prob * vig_mult),
            "away_odds": _prob_to_american(away_prob * vig_mult),
        }

    # ─── Market Comparison ────────────────────────────────────────────────────

    def compare_to_market(self, synthetic_fair_prob, market_implied_prob,
                          market_type="spread",
                          synthetic_spread=None, market_spread=None):
        """
        Compare synthetic line to market line. Detect inefficiencies.

        Args:
            synthetic_fair_prob: our model's fair probability
            market_implied_prob: market-implied probability (after vig strip)
            market_type: "spread", "moneyline", or "1x2"
            synthetic_spread: our synthetic spread (optional, for point diff)
            market_spread: market spread (optional)

        Returns:
            dict with edge, classification, spread_diff (if applicable)
        """
        edge = synthetic_fair_prob - market_implied_prob

        # Classification thresholds
        if abs(edge) < 0.02:
            classification = "sharp_agreement"
        elif abs(edge) < 0.05:
            classification = "soft_disagreement"
        else:
            classification = "hard_disagreement"

        result = {
            "edge": round(edge, 4),
            "edge_pct": round(edge * 100, 2),
            "classification": classification,
            "synthetic_prob": round(synthetic_fair_prob, 4),
            "market_prob": round(market_implied_prob, 4),
        }

        # Spread-specific analysis
        if synthetic_spread is not None and market_spread is not None:
            spread_diff = abs(synthetic_spread - market_spread)
            result["spread_diff"] = round(spread_diff, 1)
            result["stale_line"] = spread_diff > 1.5

        return result


# ─── Utility Functions ────────────────────────────────────────────────────────

def _prob_to_american(prob):
    """Convert probability to American odds."""
    if prob is None or prob <= 0 or prob >= 1:
        return None
    if prob >= 0.5:
        return round(-100 * prob / (1 - prob))
    else:
        return round(100 * (1 - prob) / prob)
