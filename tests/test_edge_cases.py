"""Cross-cutting edge case tests — None spreads, postponed games, ties, pushes, etc."""

import pytest
from unittest.mock import patch
from line_movement import detect_movement, score_line_movement, _parse_spread
from constants import get_max_score, get_recommendation, wilson_interval
from calibration import compute_raw_cover_pct
from prop_ev_engine import (
    compute_player_variance, compute_model_probability,
    american_to_implied_prob, remove_vig,
)


class TestNoneSpreads:
    """All functions should handle None/invalid spreads gracefully."""

    def test_detect_movement_none_none(self):
        d, m = detect_movement(None, None)
        assert d == "none" and m == 0.0

    def test_parse_spread_garbage(self):
        assert _parse_spread("pick'em") is None
        assert _parse_spread("PK") is None
        assert _parse_spread(float("inf")) is not None  # float passthrough

    def test_cover_pct_zero_score(self):
        assert compute_raw_cover_pct(0, "nba") == 50.0


class TestPostponedGames:
    """Postponed / cancelled games shouldn't crash analysis."""

    def test_none_scores_in_movement(self):
        d, m = detect_movement(None, "-5.5")
        assert d == "none"

    def test_variance_no_games(self):
        assert compute_player_variance([], "pts") is None

    def test_variance_none_stats(self):
        games = [{"pts": None} for _ in range(10)]
        assert compute_player_variance(games, "pts") is None


class TestTies:
    """Handle ties (regulation NHL, soccer draws)."""

    def test_zero_movement(self):
        d, m = detect_movement(-3.0, -3.0)
        assert d == "none" and m == 0.0

    def test_zero_margin_score(self):
        assert score_line_movement(0.0, "nhl") == 0


class TestPushes:
    """Push scenarios (spread hits exactly)."""

    def test_zero_edge_probability(self):
        result = compute_model_probability(25.5, 25.5, 5.0)
        assert result is not None
        assert result["prob_over"] == pytest.approx(0.5, abs=0.01)


class TestMissingElo:
    """Missing Elo ratings shouldn't crash."""

    @patch("power_ratings._elo_ratings", {"nba": {}})
    @patch("power_ratings._elo_cache_ts", 9999999999)
    def test_get_elo_unknown_team(self):
        from power_ratings import get_elo
        result = get_elo("Nonexistent Team", "nba")
        assert result == 1500  # Default initial Elo


class TestEmptyOdds:
    """Empty odds data should return safe defaults."""

    def test_remove_vig_none(self):
        assert remove_vig(None, None) is None

    def test_implied_prob_none(self):
        assert american_to_implied_prob(None) is None


class TestZeroGamePlayer:
    """Players with zero games shouldn't produce projections."""

    def test_empty_game_log(self):
        assert compute_player_variance([], "pts") is None

    def test_single_game(self):
        games = [{"pts": 25}]
        assert compute_player_variance(games, "pts") is None

    def test_four_games_insufficient(self):
        games = [{"pts": 20 + i} for i in range(4)]
        assert compute_player_variance(games, "pts") is None


class TestWilsonEdgeCases:
    def test_zero_total(self):
        lo, hi = wilson_interval(0, 0)
        assert lo == 0.0 and hi == 0.0

    def test_all_wins(self):
        lo, hi = wilson_interval(10, 10)
        assert lo > 50  # Should be high
        assert hi <= 100.0

    def test_all_losses(self):
        lo, hi = wilson_interval(0, 10)
        assert lo == 0.0
        assert hi < 50


class TestMaxScoreEdgeCases:
    def test_negative_score_cover_pct(self):
        """Negative scores should produce < 50% cover pct."""
        result = compute_raw_cover_pct(-10, "nba")
        assert result < 50.0

    def test_extreme_score(self):
        """Score way above max should produce > 95%."""
        result = compute_raw_cover_pct(100, "nba")
        assert result > 95.0


class TestRecommendationEdgeCases:
    def test_exact_boundary_nba_vegas(self):
        """Exact boundary values should return the higher tier."""
        assert get_recommendation(10, "vegas", "nba") == "STRONG PLAY"
        assert get_recommendation(7, "vegas", "nba") == "CONFIDENT"
        assert get_recommendation(5, "vegas", "nba") == "LEAN"

    def test_one_below_boundary(self):
        assert get_recommendation(9, "vegas", "nba") == "CONFIDENT"
        assert get_recommendation(6, "vegas", "nba") == "LEAN"
        assert get_recommendation(4, "vegas", "nba") == "MONITOR"
