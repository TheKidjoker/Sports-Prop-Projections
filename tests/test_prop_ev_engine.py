"""Unit tests for prop_ev_engine.py — variance, probability, EV calculations."""

import pytest
import math
from prop_ev_engine import (
    compute_player_variance, compute_combo_variance, adjust_variance,
    compute_model_probability, american_to_implied_prob,
    american_to_decimal_payout, remove_vig, calculate_ev,
    analyze_prop, classify_tier,
)


class TestComputePlayerVariance:
    def test_none_games(self):
        assert compute_player_variance(None, "pts") is None

    def test_empty_games(self):
        assert compute_player_variance([], "pts") is None

    def test_too_few_games(self):
        games = [{"pts": 20} for _ in range(4)]
        assert compute_player_variance(games, "pts") is None

    def test_five_games_sufficient(self):
        games = [{"pts": 20 + i} for i in range(5)]
        result = compute_player_variance(games, "pts")
        assert result is not None
        assert result["n_games"] == 5
        assert result["std_dev"] > 0
        assert result["mean"] > 0

    def test_exponential_weighting(self, sample_recent_games):
        """Recent games should be weighted more heavily."""
        result = compute_player_variance(sample_recent_games, "pts")
        assert result is not None
        # Weighted mean should differ from simple mean
        simple_mean = sum(g["pts"] for g in sample_recent_games) / len(sample_recent_games)
        assert result["mean"] != pytest.approx(simple_mean, abs=0.1)

    def test_bayesian_floor(self):
        """Variance should never be tiny due to Bayesian prior."""
        # All same values — zero sample variance
        games = [{"pts": 25} for _ in range(10)]
        result = compute_player_variance(games, "pts", sport="nba")
        assert result is not None
        # Should have non-zero std_dev due to Bayesian prior
        assert result["std_dev"] > 0

    def test_stat_key_mapping(self):
        games = [{"g": 1} for _ in range(6)]
        result = compute_player_variance(games, "goals", sport="nhl")
        assert result is not None

    def test_max_games_cap(self):
        games = [{"pts": 20 + i} for i in range(30)]
        result = compute_player_variance(games, "pts", max_games=10)
        assert result["n_games"] == 10


class TestComputeComboVariance:
    def test_pts_reb_ast(self, sample_recent_games):
        result = compute_combo_variance(sample_recent_games, ["pts", "reb", "ast"])
        assert result is not None
        assert result["n_games"] >= 5

    def test_missing_stat_excludes_game(self):
        games = [
            {"pts": 20, "reb": 5, "ast": 3},
            {"pts": 22, "reb": 6},  # Missing ast
            {"pts": 25, "reb": 7, "ast": 4},
            {"pts": 18, "reb": 4, "ast": 2},
            {"pts": 21, "reb": 6, "ast": 5},
            {"pts": 23, "reb": 7, "ast": 3},
        ]
        result = compute_combo_variance(games, ["pts", "reb", "ast"])
        assert result is not None
        assert result["n_games"] == 5  # Excludes 1 incomplete game

    def test_empty_stat_keys(self):
        assert compute_combo_variance([{"pts": 20}] * 5, []) is None


class TestAdjustVariance:
    def test_none_input(self):
        assert adjust_variance(None) is None

    def test_no_adjustments(self):
        assert adjust_variance(5.0) == 5.0

    def test_b2b_inflates(self):
        result = adjust_variance(5.0, is_b2b=True)
        assert result == pytest.approx(5.5, abs=0.01)

    def test_minutes_unstable(self):
        result = adjust_variance(5.0, minutes_unstable=True)
        assert result == pytest.approx(5.75, abs=0.01)

    def test_injury_boost(self):
        result = adjust_variance(5.0, has_injury_boost=True)
        assert result == pytest.approx(6.0, abs=0.01)

    def test_all_adjustments_compound(self):
        result = adjust_variance(5.0, is_b2b=True, minutes_unstable=True, has_injury_boost=True)
        # 5.0 * 1.10 * 1.15 * 1.20 = 7.59
        expected = 5.0 * 1.10 * 1.15 * 1.20
        assert result == pytest.approx(expected, abs=0.05)


class TestComputeModelProbability:
    def test_none_inputs(self):
        assert compute_model_probability(None, 25.5, 5.0) is None
        assert compute_model_probability(25.0, None, 5.0) is None
        assert compute_model_probability(25.0, 25.5, None) is None

    def test_zero_std(self):
        assert compute_model_probability(25.0, 25.5, 0) is None

    def test_projection_above_line(self):
        """Projection > line should favor OVER."""
        result = compute_model_probability(28.0, 25.5, 5.0)
        assert result is not None
        assert result["direction"] == "OVER"
        assert result["prob_over"] > 0.5

    def test_projection_below_line(self):
        """Projection < line should favor UNDER."""
        result = compute_model_probability(22.0, 25.5, 5.0)
        assert result is not None
        assert result["direction"] == "UNDER"
        assert result["prob_under"] > 0.5

    def test_projection_equals_line(self):
        """Equal projection and line should be ~50/50."""
        result = compute_model_probability(25.5, 25.5, 5.0)
        assert result["prob_over"] == pytest.approx(0.5, abs=0.01)

    def test_probability_capped(self):
        """Model probability should be capped at [0.05, 0.95]."""
        result = compute_model_probability(50.0, 25.5, 2.0)
        assert result["model_probability"] <= 0.95
        result2 = compute_model_probability(10.0, 25.5, 2.0)
        assert result2["model_probability"] >= 0.05

    def test_poisson_for_goals(self):
        """Goals stat should use Poisson distribution when projection < 5."""
        result = compute_model_probability(0.8, 0.5, 0.5, stat_key="g")
        assert result is not None
        assert result["direction"] == "OVER"

    def test_normal_for_pts(self):
        result = compute_model_probability(25.0, 24.5, 5.0, stat_key="pts")
        assert result is not None

    def test_poisson_probabilities_sum_close_to_1(self):
        result = compute_model_probability(2.5, 2.5, 1.0, stat_key="g")
        assert result is not None
        assert result["prob_over"] + result["prob_under"] == pytest.approx(1.0, abs=0.01)


class TestAmericanToImpliedProb:
    def test_minus_110(self):
        assert american_to_implied_prob(-110) == pytest.approx(0.5238, abs=0.001)

    def test_plus_150(self):
        assert american_to_implied_prob(150) == pytest.approx(0.40, abs=0.001)

    def test_minus_200(self):
        assert american_to_implied_prob(-200) == pytest.approx(0.6667, abs=0.001)

    def test_even(self):
        assert american_to_implied_prob(0) == 0.5

    def test_none(self):
        assert american_to_implied_prob(None) is None


class TestAmericanToDecimalPayout:
    def test_minus_110(self):
        result = american_to_decimal_payout(-110)
        assert result == pytest.approx(1.909, abs=0.01)

    def test_plus_150(self):
        assert american_to_decimal_payout(150) == pytest.approx(2.50, abs=0.01)

    def test_even(self):
        assert american_to_decimal_payout(0) == 2.0

    def test_none(self):
        assert american_to_decimal_payout(None) is None


class TestRemoveVig:
    def test_standard_vig(self):
        """Standard -110/-110 should give 50/50 fair, ~4.76% vig."""
        result = remove_vig(-110, -110)
        assert result is not None
        assert result["over_fair"] == pytest.approx(0.50, abs=0.01)
        assert result["under_fair"] == pytest.approx(0.50, abs=0.01)
        assert result["vig_pct"] == pytest.approx(4.76, abs=0.5)

    def test_none_odds(self):
        assert remove_vig(None, -110) is None
        assert remove_vig(-110, None) is None

    def test_asymmetric_odds(self):
        result = remove_vig(-150, 130)
        assert result is not None
        assert result["over_fair"] > result["under_fair"]
        assert result["over_fair"] + result["under_fair"] == pytest.approx(1.0, abs=0.001)


class TestCalculateEV:
    def test_positive_ev(self):
        """Higher model prob than implied = positive EV."""
        result = calculate_ev(0.60, -110)
        assert result is not None
        assert result["ev_dollars"] > 0
        assert result["ev_pct"] > 0
        assert result["edge_pct"] > 0

    def test_negative_ev(self):
        """Lower model prob than implied = negative EV."""
        result = calculate_ev(0.40, -110)
        assert result is not None
        assert result["ev_dollars"] < 0

    def test_none_inputs(self):
        assert calculate_ev(None, -110) is None
        assert calculate_ev(0.55, None) is None

    def test_breakeven(self):
        """At implied probability, EV should be ~0."""
        implied = american_to_implied_prob(-110)
        result = calculate_ev(implied, -110)
        assert result["ev_dollars"] == pytest.approx(0, abs=0.5)


class TestClassifyTier:
    def test_strong(self):
        assert classify_tier(7.0, 4.0, 15, "odds_api") == "STRONG"

    def test_confident(self):
        assert classify_tier(5.0, 2.0, 15, "odds_api") == "CONFIDENT"

    def test_lean(self):
        assert classify_tier(3.0, 1.0, 15, "odds_api") == "LEAN"

    def test_pass(self):
        assert classify_tier(1.0, 0.5, 15, "odds_api") == "PASS"

    def test_few_games_caps_at_lean(self):
        assert classify_tier(7.0, 4.0, 6, "odds_api") == "LEAN"

    def test_estimated_caps_at_confident(self):
        assert classify_tier(7.0, 4.0, 15, "estimated") == "CONFIDENT"


class TestAnalyzeProp:
    def test_none_projection(self, sample_recent_games):
        assert analyze_prop(None, 25.5, sample_recent_games, "pts") is None

    def test_none_line(self, sample_recent_games):
        assert analyze_prop(25.0, None, sample_recent_games, "pts") is None

    def test_full_analysis(self, sample_recent_games):
        result = analyze_prop(
            27.0, 25.5, sample_recent_games, "pts",
            over_odds=-110, under_odds=-110,
        )
        assert result is not None
        assert "direction" in result
        assert "model_probability" in result
        assert "ev_dollars" in result
        assert "tier" in result
        assert result["has_real_odds"] is True

    def test_estimated_odds_fallback(self, sample_recent_games):
        result = analyze_prop(27.0, 25.5, sample_recent_games, "pts")
        assert result is not None
        assert result["has_real_odds"] is False
