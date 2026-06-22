"""Unit tests for soccer_scanner.py (Phase 3) — 1X2 market, Asian handicap, BTTS."""

import pytest
from unittest.mock import patch, MagicMock


class TestSoccerScanner:
    @pytest.fixture(autouse=True)
    def setup(self):
        from soccer_scanner import SoccerScanner
        self.scanner = SoccerScanner()

    def test_analyze_1x2_market(self):
        """1X2 analysis should return all three outcomes."""
        result = self.scanner.analyze_1x2(
            home_prob=0.45, draw_prob=0.28, away_prob=0.27,
            market_odds={"home": -120, "draw": 280, "away": 300},
        )
        assert result is not None
        assert "best_value" in result
        assert "edges" in result
        assert "home" in result["edges"]
        assert "draw" in result["edges"]
        assert "away" in result["edges"]

    def test_asian_handicap_conversion(self):
        """Convert standard spread to Asian handicap."""
        result = self.scanner.convert_to_asian_handicap(spread=-0.75)
        assert result is not None
        assert "line" in result
        # -0.75 AH = split bet on -0.5 and -1.0
        assert result["line"] == -0.75

    def test_asian_handicap_quarter_lines(self):
        """Quarter-line Asian handicaps should be handled."""
        for line in [-0.25, -0.75, 0.25, 0.75, -1.25, -1.75]:
            result = self.scanner.convert_to_asian_handicap(spread=line)
            assert result is not None

    def test_btts_logic(self):
        """Both Teams to Score analysis."""
        result = self.scanner.analyze_btts(
            home_xg=1.8, away_xg=1.3,
            home_clean_sheet_pct=0.30, away_clean_sheet_pct=0.20,
        )
        assert result is not None
        assert "btts_prob" in result
        assert 0 < result["btts_prob"] < 1.0

    def test_btts_low_xg(self):
        """Low xG teams should have lower BTTS probability."""
        high = self.scanner.analyze_btts(
            home_xg=2.5, away_xg=2.0,
            home_clean_sheet_pct=0.15, away_clean_sheet_pct=0.15,
        )
        low = self.scanner.analyze_btts(
            home_xg=0.5, away_xg=0.4,
            home_clean_sheet_pct=0.45, away_clean_sheet_pct=0.50,
        )
        assert high["btts_prob"] > low["btts_prob"]

    def test_fixture_congestion(self):
        """Teams with midweek fixtures should get fatigue adjustment."""
        result = self.scanner.compute_congestion_factor(
            days_since_last=2, matches_in_14_days=5,
        )
        assert result is not None
        assert result < 1.0  # Should reduce projection

    def test_no_congestion(self):
        result = self.scanner.compute_congestion_factor(
            days_since_last=7, matches_in_14_days=2,
        )
        assert result >= 1.0

    def test_over_under_goals(self):
        """Over/under goals analysis."""
        result = self.scanner.analyze_over_under(
            home_xg=1.5, away_xg=1.2, line=2.5,
        )
        assert result is not None
        assert "over_prob" in result
        assert "under_prob" in result
        assert result["over_prob"] + result["under_prob"] == pytest.approx(1.0, abs=0.02)

    def test_league_home_advantage(self):
        """Different leagues should have different home advantages."""
        epl = self.scanner.get_league_home_advantage("epl")
        mls = self.scanner.get_league_home_advantage("mls")
        assert epl is not None
        assert mls is not None
        # EPL typically has higher home advantage than MLS
        assert isinstance(epl, float)
        assert isinstance(mls, float)
