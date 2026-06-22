"""Unit tests for prism.py — PRISM player prop projection engine."""

import pytest
from unittest.mock import patch
from prism import (
    calculate_prism_projection, _compute_rest_factor, _apply_slot_integration,
    detect_streak, calculate_minutes_volatility, estimate_line_from_average,
    _calculate_confidence, LEAGUE_AVG_TOTALS, LEAGUE_AVG_DEF,
)


class TestComputeRestFactor:
    def test_b2b_no_days_rest(self):
        assert _compute_rest_factor(True) == 0.93

    def test_no_b2b_no_days_rest(self):
        assert _compute_rest_factor(False) == 1.0

    def test_zero_days_rest(self):
        assert _compute_rest_factor(False, days_rest=0) == 0.93

    def test_one_day_rest(self):
        assert _compute_rest_factor(False, days_rest=1) == 0.97

    def test_two_days_rest(self):
        assert _compute_rest_factor(False, days_rest=2) == 1.0

    def test_three_plus_days_rest(self):
        assert _compute_rest_factor(False, days_rest=3) == 1.02
        assert _compute_rest_factor(False, days_rest=5) == 1.02

    def test_mlb_always_1(self):
        """MLB: no rest factor (162-game daily schedule)."""
        assert _compute_rest_factor(True, sport="mlb") == 1.0
        assert _compute_rest_factor(False, days_rest=0, sport="mlb") == 1.0


class TestApplySlotIntegration:
    def test_pass_small_edge(self):
        assert _apply_slot_integration(0.5, "vegas") == "PASS"
        assert _apply_slot_integration(-0.9, "public") == "PASS"

    def test_vegas_under_strong(self):
        """Vegas slot + negative edge (under) = STRONG UNDER."""
        assert _apply_slot_integration(-3.0, "vegas") == "STRONG UNDER"

    def test_vegas_over_skip(self):
        """Vegas slot + positive edge (over) = SKIP."""
        assert _apply_slot_integration(3.0, "vegas") == "SKIP"

    def test_public_over_strong(self):
        """Public slot + positive edge (over) = STRONG OVER."""
        assert _apply_slot_integration(3.0, "public") == "STRONG OVER"

    def test_public_under_lean(self):
        assert _apply_slot_integration(-3.0, "public") == "LEAN UNDER"

    def test_unknown_slot_lean(self):
        assert _apply_slot_integration(3.0, "unknown") == "LEAN OVER"
        assert _apply_slot_integration(-3.0, "unknown") == "LEAN UNDER"

    def test_small_edge_lean(self):
        """1-2 pt edge should give LEAN regardless of slot."""
        assert _apply_slot_integration(1.5, "vegas") == "LEAN OVER"
        assert _apply_slot_integration(-1.5, "public") == "LEAN UNDER"

    def test_trap_slot_same_as_vegas(self):
        assert _apply_slot_integration(-3.0, "trap") == "STRONG UNDER"


class TestDetectStreak:
    def test_too_few_games(self):
        games = [{"pts": 30}] * 4
        assert detect_streak(games, 25.5, "pts") is None

    def test_over_streak(self):
        """4 of 5 games over the line = streak."""
        games = [{"pts": v} for v in [30, 28, 26, 29, 20]]
        result = detect_streak(games, 25.5, "pts")
        assert result is not None
        assert result["direction"] == "OVER"
        assert result["count"] >= 4

    def test_under_streak(self):
        games = [{"pts": v} for v in [18, 20, 22, 19, 30]]
        result = detect_streak(games, 25.5, "pts")
        assert result is not None
        assert result["direction"] == "UNDER"
        assert result["count"] >= 4

    def test_no_streak(self):
        games = [{"pts": v} for v in [30, 20, 28, 22, 26]]
        result = detect_streak(games, 25.5, "pts")
        assert result is None

    def test_empty_games(self):
        assert detect_streak([], 25.5, "pts") is None


class TestCalculateMinutesVolatility:
    def test_empty(self):
        stdev, unstable = calculate_minutes_volatility([])
        assert stdev == 0.0
        assert unstable is False

    def test_stable_minutes(self):
        games = [{"min": 32}, {"min": 33}, {"min": 31}, {"min": 34}]
        stdev, unstable = calculate_minutes_volatility(games)
        assert stdev < 5.0
        assert unstable is False

    def test_unstable_minutes(self):
        games = [{"min": 40}, {"min": 15}, {"min": 38}, {"min": 20}, {"min": 35}]
        stdev, unstable = calculate_minutes_volatility(games)
        assert stdev > 5.0
        assert unstable is True

    def test_zero_minutes_excluded(self):
        games = [{"min": 0}, {"min": 32}, {"min": 33}, {"min": 31}]
        stdev, unstable = calculate_minutes_volatility(games)
        assert stdev >= 0


class TestEstimateLineFromAverage:
    def test_none_avg(self):
        assert estimate_line_from_average(None) is None

    def test_zero_avg(self):
        assert estimate_line_from_average(0) is None

    def test_pts_discount(self):
        result = estimate_line_from_average(25.0, "pts")
        assert result < 25.0  # Discounted
        assert result == pytest.approx(25.0 * 0.97, abs=0.1)

    def test_reb_higher_discount(self):
        result = estimate_line_from_average(8.0, "reb")
        assert result < 8.0 * 0.97  # More discount for reb

    def test_er_premium(self):
        """Earned runs line should be above average (books expect pitchers to allow more)."""
        result = estimate_line_from_average(3.0, "er")
        assert result > 3.0


class TestCalculateConfidence:
    def test_large_edge_high_confidence(self):
        result = _calculate_confidence(5.0, 7, True, None, False)
        assert result >= 80

    def test_small_edge_low_confidence(self):
        result = _calculate_confidence(0.5, 3, False, None, False)
        assert result < 50

    def test_streak_boosts(self):
        base = _calculate_confidence(3.0, 5, True, None, False)
        with_streak = _calculate_confidence(3.0, 5, True, {"direction": "OVER", "count": 4}, False)
        assert with_streak > base

    def test_unstable_reduces(self):
        base = _calculate_confidence(3.0, 5, True, None, False)
        unstable = _calculate_confidence(3.0, 5, True, None, True)
        assert unstable < base

    def test_capped_at_bounds(self):
        high = _calculate_confidence(10.0, 10, True, {"direction": "OVER", "count": 5}, False)
        low = _calculate_confidence(0.1, 1, False, None, True)
        assert 10 <= high <= 95
        assert 10 <= low <= 95


class TestCalculatePrismProjection:
    @patch("prism._get_dynamic_league_avgs", return_value=None)
    @patch("prism._get_league_matchup_avgs", return_value={})
    def test_none_season_avg(self, mock_matchup, mock_dynamic):
        result = calculate_prism_projection(
            None, [], "pts", 110.0, 112.0, 220.0,
            False, True, -5.5, [], 25.5, "vegas",
        )
        assert result is None

    @patch("prism._get_dynamic_league_avgs", return_value=None)
    @patch("prism._get_league_matchup_avgs", return_value={})
    def test_basic_projection(self, mock_matchup, mock_dynamic, sample_recent_games):
        result = calculate_prism_projection(
            25.0, sample_recent_games, "pts", 110.0, 112.0, 220.0,
            False, True, -5.5, [], 25.5, "vegas",
        )
        assert result is not None
        assert "projection" in result
        assert "edge" in result
        assert "signal" in result
        assert "confidence" in result

    @patch("prism._get_dynamic_league_avgs", return_value=None)
    @patch("prism._get_league_matchup_avgs", return_value={})
    def test_b2b_reduces_projection(self, mock_matchup, mock_dynamic, sample_recent_games):
        no_b2b = calculate_prism_projection(
            25.0, sample_recent_games, "pts", 110.0, 112.0, 220.0,
            False, True, -5.5, [], 25.5, "vegas",
        )
        with_b2b = calculate_prism_projection(
            25.0, sample_recent_games, "pts", 110.0, 112.0, 220.0,
            True, True, -5.5, [], 25.5, "vegas",
        )
        assert with_b2b["projection"] < no_b2b["projection"]

    @patch("prism._get_dynamic_league_avgs", return_value=None)
    @patch("prism._get_league_matchup_avgs", return_value={})
    def test_estimated_line_caps_signal(self, mock_matchup, mock_dynamic, sample_recent_games):
        """Estimated lines should never produce STRONG signals."""
        result = calculate_prism_projection(
            30.0, sample_recent_games, "pts", 115.0, 112.0, 230.0,
            False, True, -1.0, [], None, "public",
        )
        if result and result["signal"].startswith("STRONG"):
            pytest.fail("Estimated lines should cap at LEAN")

    @patch("prism._get_dynamic_league_avgs", return_value=None)
    @patch("prism._get_league_matchup_avgs", return_value={})
    def test_blowout_discount(self, mock_matchup, mock_dynamic, sample_recent_games):
        """Large spreads should reduce points projection."""
        normal = calculate_prism_projection(
            25.0, sample_recent_games, "pts", 110.0, 112.0, 220.0,
            False, True, -3.0, [], 25.5, "vegas",
        )
        blowout = calculate_prism_projection(
            25.0, sample_recent_games, "pts", 110.0, 112.0, 220.0,
            False, True, -15.0, [], 25.5, "vegas",
        )
        assert blowout["projection"] < normal["projection"]

    @patch("prism._get_dynamic_league_avgs", return_value=None)
    @patch("prism._get_league_matchup_avgs", return_value={})
    def test_injury_usage_boost(self, mock_matchup, mock_dynamic, sample_recent_games):
        """Injured teammates should boost points projection."""
        no_injuries = calculate_prism_projection(
            25.0, sample_recent_games, "pts", 110.0, 112.0, 220.0,
            False, True, -5.5, [], 25.5, "vegas", player_rank=0,
        )
        with_injuries = calculate_prism_projection(
            25.0, sample_recent_games, "pts", 110.0, 112.0, 220.0,
            False, True, -5.5, [{"name": "Star", "ppg": 28.0}],
            25.5, "vegas", player_rank=0,
        )
        assert with_injuries["projection"] > no_injuries["projection"]
