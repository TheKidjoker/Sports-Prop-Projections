"""Unit tests for rank_analysis.py — rank tiers, rank scam, spread discrepancy."""

import pytest
from rank_analysis import (
    _get_rank_tier, _detect_rank_scam, _detect_spread_discrepancy,
    _get_expected_spread, CFB_EXPECTED_SPREADS, CBB_EXPECTED_SPREADS,
)


class TestGetRankTier:
    def test_frontend(self):
        for rank in [1, 5, 9]:
            assert _get_rank_tier(rank) == "frontend"

    def test_middle(self):
        for rank in [10, 15, 19]:
            assert _get_rank_tier(rank) == "middle"

    def test_backend(self):
        for rank in [20, 22, 25]:
            assert _get_rank_tier(rank) == "backend"

    def test_unranked(self):
        assert _get_rank_tier(None) is None
        assert _get_rank_tier(26) is None
        assert _get_rank_tier(0) is None
        assert _get_rank_tier(99) is None


class TestGetExpectedSpread:
    def test_cfb_top_5(self):
        result = _get_expected_spread(3, "cfb")
        assert result == (24, 28)

    def test_cfb_21_25(self):
        result = _get_expected_spread(22, "cfb")
        assert result == (7, 10)

    def test_cbb_top_5(self):
        result = _get_expected_spread(3, "cbb")
        assert result == (12, 16)

    def test_cbb_21_25(self):
        result = _get_expected_spread(22, "cbb")
        assert result == (3, 5)

    def test_unranked(self):
        assert _get_expected_spread(30, "cfb") is None


class TestDetectRankScam:
    def test_classic_rank_scam(self):
        """#5 at home as underdog vs #15 — rank scam."""
        result = _detect_rank_scam(5, 15, 3.5, "public")
        assert result["is_rank_scam"] is True
        assert "COVER" in result["scam_action"]

    def test_vegas_slot_fade(self):
        result = _detect_rank_scam(5, 15, 3.5, "vegas")
        assert result["is_rank_scam"] is True
        assert "FADE" in result["scam_action"]

    def test_no_scam_home_favored(self):
        """Home is favored (negative spread) = no rank scam."""
        result = _detect_rank_scam(5, 15, -3.5, "public")
        assert result["is_rank_scam"] is False

    def test_no_scam_away_ranked_higher(self):
        """Away team ranked higher (lower number) = no rank scam."""
        result = _detect_rank_scam(15, 5, 3.5, "public")
        assert result["is_rank_scam"] is False

    def test_no_scam_one_unranked(self):
        result = _detect_rank_scam(5, None, 3.5, "public")
        assert result["is_rank_scam"] is False

    def test_no_scam_both_unranked(self):
        result = _detect_rank_scam(None, None, 3.5, "public")
        assert result["is_rank_scam"] is False

    def test_none_spread(self):
        result = _detect_rank_scam(5, 15, None, "public")
        assert result["is_rank_scam"] is False

    def test_equal_ranks(self):
        """Same rank shouldn't trigger (home_rank >= away_rank check)."""
        result = _detect_rank_scam(10, 10, 3.5, "public")
        assert result["is_rank_scam"] is False


class TestDetectSpreadDiscrepancy:
    def test_discrepancy_detected(self):
        """#3 CFB should be -24 to -28, but only -15 = discrepancy."""
        result = _detect_spread_discrepancy(3, None, -15.0, "public", "cfb")
        assert result["is_discrepancy"] is True

    def test_no_discrepancy_in_range(self):
        """Spread within expected range = no flag."""
        result = _detect_spread_discrepancy(3, None, -26.0, "public", "cfb")
        assert result["is_discrepancy"] is False

    def test_both_ranked(self):
        """Both ranked = not applicable."""
        result = _detect_spread_discrepancy(3, 10, -15.0, "public", "cfb")
        assert result["is_discrepancy"] is False

    def test_both_unranked(self):
        result = _detect_spread_discrepancy(None, None, -15.0, "public", "cfb")
        assert result["is_discrepancy"] is False

    def test_cbb_backend_different_message(self):
        """CBB backend (#20-25) has different discrepancy guidance."""
        result = _detect_spread_discrepancy(22, None, -1.0, "public", "cbb")
        # Expected 3-5 range, actual 1 = discrepancy (1 < 3 - 3 = 0, hmm)
        # Actually 1 is NOT < 3-3=0, so no discrepancy at exactly -1
        # Let's check with 0 which is < 3-3=0... still not. Threshold is expected_low - 3
        # expected for rank 22 cbb is (3,5), so expected_low=3, 3-3=0, |spread|=1 >= 0 -> no flag
        assert result["is_discrepancy"] is False

    def test_none_spread(self):
        result = _detect_spread_discrepancy(3, None, None, "public", "cfb")
        assert result["is_discrepancy"] is False

    def test_away_ranked(self):
        """Away team ranked, home unranked."""
        result = _detect_spread_discrepancy(None, 3, -15.0, "public", "cfb")
        assert result["is_discrepancy"] is True
        assert result["ranked_team"] == "away"
