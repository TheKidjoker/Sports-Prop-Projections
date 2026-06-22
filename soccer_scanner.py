# ─── Soccer Match Scanner ─────────────────────────────────────────────────────
# Analyzes soccer matches: 1X2 probabilities, Asian handicap edge,
# Over/Under goals, Both Teams to Score (BTTS).

import math
import logging
from scipy.stats import poisson
from constants import SOCCER_LEAGUES
from soccer_ev_model import SoccerEVModel
from market_maker import SyntheticMarketMaker
from vig_analysis import strip_vig_3way
from prop_ev_engine import american_to_implied_prob

logger = logging.getLogger(__name__)

# League-specific home advantage rates (historical averages)
_LEAGUE_HOME_ADVANTAGE = {
    "epl": 0.46,
    "la_liga": 0.47,
    "bundesliga": 0.44,
    "serie_a": 0.46,
    "ligue_1": 0.45,
    "mls": 0.50,
    "ucl": 0.42,
    "eredivisie": 0.45,
    "liga_portugal": 0.47,
    "super_lig": 0.48,
    "championship": 0.45,
    "liga_mx": 0.49,
    "a_league": 0.46,
    "j_league": 0.47,
    "k_league": 0.46,
    "saudi_pro": 0.48,
}


class SoccerScanner:
    """
    Soccer match analysis engine.
    Supports 1X2, Asian handicap, O/U goals, BTTS markets.
    """

    def __init__(self):
        self._ev_model = SoccerEVModel()
        self._market_maker = SyntheticMarketMaker()

    def scan_matches(self, league, date_str=None):
        """
        Scan all matches for a league on a date.

        Args:
            league: league key (e.g., "epl")
            date_str: YYYY-MM-DD or None for today

        Returns:
            list of analyzed match dicts, sorted by edge
        """
        league_config = SOCCER_LEAGUES.get(league)
        if not league_config:
            logger.warning("[soccer] Unknown league: %s", league)
            return []

        try:
            from api_soccer import get_fixtures
            fixtures = get_fixtures(league_config["api_id"], date_str)
        except Exception as e:
            logger.warning("[soccer] Failed to fetch fixtures: %s", e)
            return []

        if not fixtures:
            return []

        results = []
        for match in fixtures:
            if match.get("status") not in ("NS", "TBD", None):
                continue  # Skip in-progress or finished matches

            analysis = self._analyze_match(match, league)
            if analysis:
                results.append(analysis)

        # Sort by absolute edge (best opportunities first)
        results.sort(key=lambda x: abs(x.get("best_edge", 0)), reverse=True)
        return results

    def _analyze_match(self, match, league):
        """
        Full analysis of a single soccer match.

        Returns:
            dict with 1X2 probabilities, Asian handicap, O/U, BTTS
        """
        home = match.get("home_team", "Unknown")
        away = match.get("away_team", "Unknown")

        # Generate 1X2 from market maker
        market_1x2 = self._market_maker.generate_1x2(home, away, league)

        # Over/under analysis (default 2.5 line)
        ou_analysis = self.analyze_over_under(
            home_xg=market_1x2.get("home_prob", 0.45) * 2.7,  # Rough xG proxy
            away_xg=market_1x2.get("away_prob", 0.30) * 2.7,
            line=2.5,
        )

        # BTTS analysis
        btts = self.analyze_btts(
            home_xg=market_1x2.get("home_prob", 0.45) * 2.7,
            away_xg=market_1x2.get("away_prob", 0.30) * 2.7,
            home_clean_sheet_pct=0.30,  # Default until we have real data
            away_clean_sheet_pct=0.25,
        )

        # Find best edge across all markets
        edges = {
            "home_1x2": market_1x2.get("home_prob", 0) - 0.33,
            "draw_1x2": market_1x2.get("draw_prob", 0) - 0.33,
            "away_1x2": market_1x2.get("away_prob", 0) - 0.33,
        }
        best_market = max(edges, key=lambda k: abs(edges[k]))
        best_edge = edges[best_market]

        return {
            "fixture_id": match.get("fixture_id"),
            "home_team": home,
            "away_team": away,
            "date": match.get("date"),
            "venue": match.get("venue"),
            "league": league,
            "league_name": SOCCER_LEAGUES.get(league, {}).get("name", league),
            "match_result_1x2": {
                "home_prob": market_1x2.get("home_prob"),
                "draw_prob": market_1x2.get("draw_prob"),
                "away_prob": market_1x2.get("away_prob"),
                "home_odds": market_1x2.get("home_odds"),
                "draw_odds": market_1x2.get("draw_odds"),
                "away_odds": market_1x2.get("away_odds"),
            },
            "over_under": ou_analysis,
            "btts": btts,
            "best_edge": round(best_edge, 4),
            "best_market": best_market,
        }

    # ─── 1X2 Market Analysis ──────────────────────────────────────────────────

    def analyze_1x2(self, home_prob, draw_prob, away_prob, market_odds=None):
        """
        Analyze 1X2 market: compare model probs to market odds.

        Args:
            home_prob: model P(home win)
            draw_prob: model P(draw)
            away_prob: model P(away win)
            market_odds: dict with "home", "draw", "away" American odds

        Returns:
            dict with edges for each outcome and best value
        """
        edges = {"home": 0, "draw": 0, "away": 0}
        best_value = None
        best_edge = 0

        if market_odds:
            fair = strip_vig_3way(
                market_odds.get("home", -120),
                market_odds.get("draw", 280),
                market_odds.get("away", 300),
            )
            if fair:
                edges["home"] = round(home_prob - fair["home_fair"], 4)
                edges["draw"] = round(draw_prob - fair["draw_fair"], 4)
                edges["away"] = round(away_prob - fair["away_fair"], 4)

                # Best value = largest positive edge
                for outcome, edge in edges.items():
                    if edge > best_edge:
                        best_edge = edge
                        best_value = outcome

        return {
            "edges": edges,
            "best_value": best_value,
            "best_edge": round(best_edge, 4),
        }

    # ─── Asian Handicap ──────────────────────────────────────────────────────

    def convert_to_asian_handicap(self, spread):
        """
        Convert a standard spread to Asian Handicap notation.

        Asian handicaps use quarter-line increments (0.25, 0.75)
        which split the bet across two lines.

        Args:
            spread: standard spread (e.g., -0.75)

        Returns:
            dict with line, split_lines (if quarter line), description
        """
        if spread is None:
            return None

        # Determine if it's a quarter line (split bet)
        remainder = abs(spread) % 0.5
        is_quarter = abs(remainder - 0.25) < 0.01

        if is_quarter:
            # Quarter line = split bet on two half-lines
            lower = math.floor(spread * 2) / 2
            upper = math.ceil(spread * 2) / 2
            return {
                "line": spread,
                "is_split": True,
                "split_lines": [lower, upper],
                "description": f"AH {spread:+.2f} (split: {lower:+.1f} / {upper:+.1f})",
            }

        return {
            "line": spread,
            "is_split": False,
            "split_lines": [spread],
            "description": f"AH {spread:+.1f}",
        }

    # ─── Over/Under Goals ────────────────────────────────────────────────────

    def analyze_over_under(self, home_xg, away_xg, line=2.5):
        """
        Analyze over/under goals market using Poisson distribution.

        Args:
            home_xg: expected goals for home team
            away_xg: expected goals for away team
            line: total goals line (default 2.5)

        Returns:
            dict with over_prob, under_prob, expected_total
        """
        total_xg = (home_xg or 1.35) + (away_xg or 1.35)

        # Use Poisson distribution for integer goal totals
        # P(total > 2.5) = 1 - P(0) - P(1) - P(2)
        k = int(math.floor(line))
        under_prob = poisson.cdf(k, total_xg)
        over_prob = 1.0 - under_prob

        return {
            "line": line,
            "over_prob": round(over_prob, 4),
            "under_prob": round(under_prob, 4),
            "expected_total": round(total_xg, 2),
        }

    # ─── Both Teams to Score (BTTS) ──────────────────────────────────────────

    def analyze_btts(self, home_xg, away_xg,
                     home_clean_sheet_pct=0.30, away_clean_sheet_pct=0.25):
        """
        Estimate BTTS probability.

        BTTS Yes = both teams score at least 1 goal.
        P(BTTS) = P(home scores) * P(away scores)
        P(team scores) = 1 - P(0 goals) = 1 - Poisson(0, xG)

        Args:
            home_xg: home team's expected goals
            away_xg: away team's expected goals
            home_clean_sheet_pct: home team's clean sheet rate
            away_clean_sheet_pct: away team's clean sheet rate

        Returns:
            dict with btts_prob, btts_yes_fair_odds
        """
        home_xg = max(home_xg or 0.5, 0.1)
        away_xg = max(away_xg or 0.5, 0.1)

        # Poisson-based scoring probability
        p_home_scores_poisson = 1.0 - poisson.pmf(0, home_xg)
        p_away_scores_poisson = 1.0 - poisson.pmf(0, away_xg)

        # Blend with clean sheet data if available
        p_home_scores = (p_home_scores_poisson + (1 - away_clean_sheet_pct)) / 2
        p_away_scores = (p_away_scores_poisson + (1 - home_clean_sheet_pct)) / 2

        btts_prob = p_home_scores * p_away_scores

        return {
            "btts_prob": round(btts_prob, 4),
            "btts_no_prob": round(1.0 - btts_prob, 4),
            "home_scoring_prob": round(p_home_scores, 4),
            "away_scoring_prob": round(p_away_scores, 4),
        }

    # ─── Fixture Congestion ──────────────────────────────────────────────────

    def compute_congestion_factor(self, days_since_last, matches_in_14_days):
        """
        Compute fatigue/congestion factor for fixture-heavy periods.

        Args:
            days_since_last: days since team's last competitive match
            matches_in_14_days: number of matches in last 14 days

        Returns:
            float multiplier (< 1.0 = fatigued, >= 1.0 = rested)
        """
        # Base: well-rested
        factor = 1.0

        # Short rest penalty
        if days_since_last <= 2:
            factor *= 0.93
        elif days_since_last == 3:
            factor *= 0.97

        # High match density penalty
        if matches_in_14_days >= 5:
            factor *= 0.92
        elif matches_in_14_days >= 4:
            factor *= 0.96

        return round(factor, 3)

    # ─── League Home Advantage ────────────────────────────────────────────────

    def get_league_home_advantage(self, league):
        """Get historical home win rate for a league."""
        return _LEAGUE_HOME_ADVANTAGE.get(league, 0.45)


# ─── Module-level scanner instance ───────────────────────────────────────────
_scanner = None


def get_scanner():
    global _scanner
    if _scanner is None:
        _scanner = SoccerScanner()
    return _scanner
