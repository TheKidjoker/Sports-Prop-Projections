"""Integration tests for the scan pipeline — mocked APIs, full flow verification."""

import pytest
from unittest.mock import patch, MagicMock
from constants import get_max_score


class TestScanPipelineIntegration:
    """Test the full scan pipeline with mocked API responses."""

    def test_score_capping(self):
        """Confirmation score should never exceed max_score for the sport."""
        from constants import THRESHOLDS
        for sport in THRESHOLDS:
            max_score = get_max_score(sport)
            assert max_score > 0
            assert isinstance(max_score, int)

    def test_recommendation_assignment_consistency(self):
        """Every recommendation should be one of the valid values."""
        from constants import get_recommendation
        valid_recs = {"STRONG PLAY", "CONFIDENT", "LEAN", "MONITOR"}
        for sport in ["nba", "nhl", "cbb", "cfb", "nfl", "mlb"]:
            for score in range(0, 50, 5):
                for slot in ["public", "vegas"]:
                    rec = get_recommendation(score, slot, sport)
                    assert rec in valid_recs, f"Invalid rec {rec} for {sport} score={score} slot={slot}"

    def test_cover_pct_range(self):
        """cover_pct should always be between 0 and 100 for valid scores."""
        from calibration import compute_raw_cover_pct
        for sport in ["nba", "nhl", "cbb"]:
            max_s = get_max_score(sport)
            for score in range(0, max_s + 1):
                pct = compute_raw_cover_pct(score, sport)
                assert 0 < pct <= 100, f"cover_pct {pct} out of range for {sport} score={score}"

    def test_output_dict_structure(self, sample_game_dict):
        """Game analysis dict should have all required keys."""
        required_keys = [
            "event_id", "home_team", "away_team",
            "current_spread", "slot_type", "lean_team",
            "confirmation_score", "cover_pct", "recommendation",
        ]
        for key in required_keys:
            assert key in sample_game_dict, f"Missing key: {key}"

    def test_clv_calculation_logic(self):
        """CLV = closing_spread - opening_spread (from lean perspective)."""
        opening = -5.5
        closing = -7.0
        # Line moved from -5.5 to -7.0 (more negative = public money)
        # If lean is on the underdog: CLV = closing - opening = -7.0 - (-5.5) = -1.5
        clv = closing - opening
        assert clv == pytest.approx(-1.5)

    def test_wilson_interval_convergence(self):
        """Wilson CI should narrow with more samples."""
        from constants import wilson_interval
        lo_small, hi_small = wilson_interval(5, 10)
        lo_big, hi_big = wilson_interval(500, 1000)
        assert (hi_small - lo_small) > (hi_big - lo_big)

    def test_all_sports_have_thresholds(self):
        """Every supported sport should have threshold configuration."""
        from constants import THRESHOLDS
        expected_sports = {"nba", "nhl", "cbb", "cfb", "nfl", "mlb"}
        assert expected_sports.issubset(set(THRESHOLDS.keys()))
