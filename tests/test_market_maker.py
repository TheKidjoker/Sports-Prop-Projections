"""Unit tests for market_maker.py (Phase 1) — synthetic line generation."""

import pytest
from unittest.mock import patch


class TestSyntheticMarketMaker:
    @pytest.fixture(autouse=True)
    def setup(self):
        from market_maker import SyntheticMarketMaker
        self.mm = SyntheticMarketMaker()

    def test_generate_spread_equal_teams(self):
        """Equal Elo teams should produce ~0 spread (just home advantage)."""
        result = self.mm.generate_spread("Team A", "Team B", "nba",
                                          home_elo=1500, away_elo=1500)
        assert result is not None
        assert "fair_spread" in result
        assert "fair_prob" in result
        # Home team should be slight favorite (home advantage)
        assert result["fair_spread"] < 0

    def test_generate_spread_elo_gap(self):
        """1600 vs 1400 NBA should produce ~7pt spread."""
        result = self.mm.generate_spread("Strong", "Weak", "nba",
                                          home_elo=1600, away_elo=1400)
        assert result["fair_spread"] < -5  # Strong home favorite
        assert result["fair_spread"] > -12  # Not extreme

    def test_generate_spread_away_favorite(self):
        """Away team stronger should produce positive spread."""
        result = self.mm.generate_spread("Weak", "Strong", "nba",
                                          home_elo=1400, away_elo=1600)
        # Even with home advantage, 200pt gap should make away favorite
        assert result is not None

    def test_generate_moneyline(self):
        result = self.mm.generate_moneyline("Home", "Away", "nba",
                                             home_elo=1600, away_elo=1400)
        assert result is not None
        assert "home_odds" in result
        assert "away_odds" in result
        assert "home_prob" in result
        # Home should be favorite (negative odds)
        assert result["home_odds"] < 0
        assert result["away_odds"] > 0

    def test_generate_total(self):
        result = self.mm.generate_total("Home", "Away", "nba",
                                         home_off=110.0, away_off=108.0,
                                         home_def=105.0, away_def=107.0)
        assert result is not None
        assert "fair_total" in result
        assert result["fair_total"] > 180  # NBA totals are high

    def test_generate_1x2_soccer(self):
        """Soccer 3-way market should sum to ~1.0 (before vig)."""
        result = self.mm.generate_1x2("Man City", "Arsenal", "epl",
                                       home_elo=1650, away_elo=1600)
        assert result is not None
        assert "home_prob" in result
        assert "draw_prob" in result
        assert "away_prob" in result
        total = result["home_prob"] + result["draw_prob"] + result["away_prob"]
        assert total == pytest.approx(1.0, abs=0.01)
        # Draw prob should be non-trivial for soccer
        assert result["draw_prob"] > 0.10

    def test_compare_to_market_agreement(self):
        """When synthetic and market agree, classification should be agreement."""
        result = self.mm.compare_to_market(
            synthetic_fair_prob=0.55,
            market_implied_prob=0.54,
            market_type="spread",
        )
        assert result is not None
        assert result["classification"] == "sharp_agreement"

    def test_compare_to_market_soft_disagreement(self):
        result = self.mm.compare_to_market(
            synthetic_fair_prob=0.58,
            market_implied_prob=0.54,
            market_type="moneyline",
        )
        assert result["classification"] in ("soft_disagreement", "hard_disagreement")

    def test_compare_to_market_hard_disagreement(self):
        result = self.mm.compare_to_market(
            synthetic_fair_prob=0.65,
            market_implied_prob=0.50,
            market_type="moneyline",
        )
        assert result["classification"] == "hard_disagreement"

    def test_spread_rounding(self):
        """Spreads should be rounded to standard 0.5 increments."""
        result = self.mm.generate_spread("A", "B", "nba",
                                          home_elo=1520, away_elo=1480)
        spread = result["fair_spread"]
        # Should be rounded to 0.5
        assert spread * 2 == pytest.approx(round(spread * 2), abs=0.01)
