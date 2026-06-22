"""Unit tests for power_ratings.py — Elo math, MOV multiplier, rating updates."""

import pytest
import math
from power_ratings import (
    _expected_score, _mov_multiplier, _update_elo, ELO_CONFIG,
)


class TestExpectedScore:
    def test_equal_ratings(self):
        """Equal Elo ratings should give 0.5 expected score."""
        assert _expected_score(1500, 1500) == pytest.approx(0.5)

    def test_400_gap_favored(self):
        """400 point gap: strong team ~0.909 expected."""
        result = _expected_score(1900, 1500)
        assert result == pytest.approx(0.909, abs=0.01)

    def test_400_gap_underdog(self):
        """Underdog should get ~0.091."""
        result = _expected_score(1500, 1900)
        assert result == pytest.approx(0.091, abs=0.01)

    def test_symmetry(self):
        """expected_score(A, B) + expected_score(B, A) == 1.0."""
        a = _expected_score(1600, 1400)
        b = _expected_score(1400, 1600)
        assert a + b == pytest.approx(1.0)

    def test_200_gap(self):
        """200 point gap: ~0.76 expected."""
        result = _expected_score(1700, 1500)
        assert result == pytest.approx(0.76, abs=0.02)

    def test_result_between_0_and_1(self):
        assert 0 < _expected_score(1200, 1800) < 1
        assert 0 < _expected_score(1800, 1200) < 1


class TestMOVMultiplier:
    def test_close_game(self):
        """Close games (1-pt margin) should have small multiplier."""
        mult = _mov_multiplier(1, 0)
        assert mult > 0.5  # Floor
        assert mult < 2.0

    def test_blowout(self):
        """Blowouts have diminishing returns via log."""
        mult_small = _mov_multiplier(5, 0)
        mult_large = _mov_multiplier(30, 0)
        # Diminishing returns — 30pt should NOT be 6x of 5pt
        assert mult_large < mult_small * 3

    def test_elo_diff_adjustment(self):
        """Bigger Elo gap = smaller multiplier (expected blowout less impressive)."""
        mult_no_gap = _mov_multiplier(10, 0)
        mult_big_gap = _mov_multiplier(10, 400)
        assert mult_big_gap < mult_no_gap

    def test_floor(self):
        """Multiplier should never go below 0.5."""
        mult = _mov_multiplier(0.1, 1000)
        assert mult >= 0.5

    def test_zero_margin(self):
        """Zero margin should give ~0.5 (floor)."""
        mult = _mov_multiplier(0, 0)
        assert mult == 0.5


class TestUpdateElo:
    def test_winner_gains_loser_loses(self):
        """Winner should gain Elo, loser should lose."""
        new_w, new_l = _update_elo(1500, 1500, 10, 20)
        assert new_w > 1500
        assert new_l < 1500

    def test_conservation(self):
        """Total Elo should be roughly conserved (within MOV adjustment)."""
        new_w, new_l = _update_elo(1500, 1500, 10, 20)
        # With MOV multiplier, not exactly conserved but close
        total = new_w + new_l
        assert abs(total - 3000) < 1  # Very close to conserved

    def test_upset_larger_swing(self):
        """Upset (lower rated wins) should produce larger Elo swing."""
        # Underdog wins
        new_w_upset, new_l_upset = _update_elo(1400, 1600, 10, 20)
        # Favorite wins
        new_w_expected, new_l_expected = _update_elo(1600, 1400, 10, 20)

        upset_gain = new_w_upset - 1400
        expected_gain = new_w_expected - 1600
        assert upset_gain > expected_gain

    def test_no_mov(self):
        """Without MOV multiplier, pure Elo update."""
        new_w, new_l = _update_elo(1500, 1500, 10, 20, use_mov=False)
        # K * (1 - 0.5) = 20 * 0.5 = 10 points change
        assert new_w == pytest.approx(1510.0, abs=0.5)
        assert new_l == pytest.approx(1490.0, abs=0.5)

    def test_k_factor_scales_update(self):
        """Higher K-factor = larger update."""
        new_w_low, _ = _update_elo(1500, 1500, 10, 10)
        new_w_high, _ = _update_elo(1500, 1500, 10, 30)
        assert (new_w_high - 1500) > (new_w_low - 1500)


class TestEloConfig:
    def test_all_sports_have_config(self):
        expected_sports = {"nba", "nhl", "cbb", "nfl", "cfb", "mlb"}
        assert expected_sports.issubset(set(ELO_CONFIG.keys()))

    def test_initial_elo_is_1500(self):
        for sport, config in ELO_CONFIG.items():
            assert config["initial_elo"] == 1500, f"{sport} should start at 1500"

    def test_season_carry_between_0_and_1(self):
        for sport, config in ELO_CONFIG.items():
            assert 0 < config["season_carry"] < 1, f"{sport} carry out of range"

    def test_k_factor_positive(self):
        for sport, config in ELO_CONFIG.items():
            assert config["k_factor"] > 0, f"{sport} needs positive K"

    def test_home_advantage_positive(self):
        for sport, config in ELO_CONFIG.items():
            assert config["home_advantage"] > 0, f"{sport} needs positive home adv"
