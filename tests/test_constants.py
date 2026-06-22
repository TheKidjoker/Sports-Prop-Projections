"""Unit tests for constants.py — thresholds, recommendations, Wilson CI, z-test."""

import pytest
from constants import (
    get_max_score, get_recommendation, wilson_interval, metric_with_ci,
    proportion_z_test, THRESHOLDS, get_override, SPORT_OVERRIDES,
)


class TestGetMaxScore:
    def test_nba(self):
        assert get_max_score("nba") == 44

    def test_nhl(self):
        assert get_max_score("nhl") == 25

    def test_cbb(self):
        assert get_max_score("cbb") == 38

    def test_cfb(self):
        assert get_max_score("cfb") == 35

    def test_nfl(self):
        assert get_max_score("nfl") == 35

    def test_mlb(self):
        assert get_max_score("mlb") == 25

    def test_unknown_sport_defaults_to_nhl(self):
        """Unknown sports should fallback to NHL thresholds."""
        assert get_max_score("curling") == 25  # NHL max


class TestGetRecommendation:
    # NBA (slot-dependent thresholds)
    def test_nba_vegas_strong(self):
        assert get_recommendation(10, "vegas", "nba") == "STRONG PLAY"

    def test_nba_vegas_confident(self):
        assert get_recommendation(7, "vegas", "nba") == "CONFIDENT"

    def test_nba_vegas_lean(self):
        assert get_recommendation(5, "vegas", "nba") == "LEAN"

    def test_nba_vegas_monitor(self):
        assert get_recommendation(3, "vegas", "nba") == "MONITOR"

    def test_nba_public_strong(self):
        assert get_recommendation(10, "public", "nba") == "STRONG PLAY"

    def test_nba_public_lean(self):
        assert get_recommendation(7, "public", "nba") == "LEAN"

    def test_nba_public_monitor(self):
        assert get_recommendation(5, "public", "nba") == "MONITOR"

    # NHL (slot-dependent)
    def test_nhl_vegas_strong(self):
        assert get_recommendation(7, "vegas", "nhl") == "STRONG PLAY"

    def test_nhl_vegas_lean(self):
        assert get_recommendation(3, "vegas", "nhl") == "LEAN"

    def test_nhl_vegas_monitor(self):
        assert get_recommendation(2, "vegas", "nhl") == "MONITOR"

    def test_nhl_public_lean(self):
        assert get_recommendation(5, "public", "nhl") == "LEAN"

    def test_nhl_public_monitor(self):
        assert get_recommendation(3, "public", "nhl") == "MONITOR"

    # CBB/CFB/NFL (flat thresholds)
    def test_cbb_strong(self):
        assert get_recommendation(13, "any", "cbb") == "STRONG PLAY"

    def test_cbb_lean(self):
        assert get_recommendation(10, "any", "cbb") == "LEAN"

    def test_cbb_monitor(self):
        assert get_recommendation(5, "any", "cbb") == "MONITOR"

    def test_nfl_strong(self):
        assert get_recommendation(15, "any", "nfl") == "STRONG PLAY"

    def test_nfl_lean(self):
        assert get_recommendation(8, "any", "nfl") == "LEAN"

    def test_mlb_strong(self):
        assert get_recommendation(7, "any", "mlb") == "STRONG PLAY"

    def test_mlb_lean(self):
        assert get_recommendation(4, "any", "mlb") == "LEAN"

    # Edge: unknown sport fallback
    def test_unknown_sport_uses_cfb_fallback(self):
        # cfb thresholds: strong=11, lean=9
        assert get_recommendation(11, "vegas", "unknown_sport") == "STRONG PLAY"
        assert get_recommendation(9, "vegas", "unknown_sport") == "LEAN"
        assert get_recommendation(5, "vegas", "unknown_sport") == "MONITOR"

    def test_zero_score(self):
        assert get_recommendation(0, "vegas", "nba") == "MONITOR"

    def test_max_score(self):
        assert get_recommendation(44, "vegas", "nba") == "STRONG PLAY"


class TestWilsonInterval:
    def test_zero_total(self):
        lower, upper = wilson_interval(0, 0)
        assert lower == 0.0
        assert upper == 0.0

    def test_perfect_score(self):
        lower, upper = wilson_interval(1, 1)
        assert lower > 0
        assert upper <= 100.0

    def test_half_success(self):
        lower, upper = wilson_interval(50, 100)
        assert 40 < lower < 50
        assert 50 < upper < 60

    def test_large_sample(self):
        lower, upper = wilson_interval(500, 1000)
        # Tight CI with large sample
        assert upper - lower < 10

    def test_asymmetric_small_sample(self):
        lower, upper = wilson_interval(3, 5)
        # Wilson handles small samples better than normal approximation
        assert lower > 0
        assert upper < 100

    def test_all_failures(self):
        lower, upper = wilson_interval(0, 100)
        assert lower == 0.0
        assert upper > 0  # Not exactly 0 due to Wilson correction


class TestMetricWithCI:
    def test_zero_total(self):
        result = metric_with_ci(0, 0)
        assert result["value"] == 0
        assert result["below_minimum"] is True

    def test_sufficient_sample(self):
        result = metric_with_ci(60, 100, min_sample=50)
        assert result["value"] == 60.0
        assert result["below_minimum"] is False
        assert result["ci_lower"] < 60
        assert result["ci_upper"] > 60

    def test_below_minimum(self):
        result = metric_with_ci(5, 10, min_sample=30)
        assert result["below_minimum"] is True
        assert result["n"] == 10

    def test_no_min_sample(self):
        result = metric_with_ci(5, 10)
        assert result["below_minimum"] is False


class TestProportionZTest:
    def test_zero_total(self):
        z, p = proportion_z_test(0, 0)
        assert z == 0.0
        assert p == 1.0

    def test_at_baseline(self):
        z, p = proportion_z_test(50, 100, baseline=0.50)
        assert z == pytest.approx(0.0, abs=0.01)
        assert p > 0.9

    def test_above_baseline(self):
        z, p = proportion_z_test(70, 100, baseline=0.50)
        assert z > 0
        assert p < 0.05  # Significant

    def test_below_baseline(self):
        z, p = proportion_z_test(30, 100, baseline=0.50)
        assert z < 0
        assert p < 0.05


class TestGetOverride:
    def test_validated_override(self):
        val = get_override("nba", "tuesday_penalty", 0)
        assert val == -3

    def test_weak_override_returns_default(self):
        val = get_override("nhl", "b2b_bonus", 99)
        assert val == 99  # weak confidence, returns default

    def test_missing_override(self):
        val = get_override("nba", "nonexistent_key", 42)
        assert val == 42

    def test_missing_sport(self):
        val = get_override("curling", "any_key", 7)
        assert val == 7
