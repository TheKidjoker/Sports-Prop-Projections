"""Regression pinning tests — known inputs -> exact expected outputs."""

import pytest
from constants import get_max_score, get_recommendation
from calibration import compute_raw_cover_pct
from line_movement import detect_movement, score_line_movement, confirms_slot
from prop_ev_engine import (
    american_to_implied_prob, american_to_decimal_payout,
    remove_vig, compute_model_probability,
)
from power_ratings import _expected_score, _mov_multiplier


class TestRegressionPins:
    """Pin known good values to catch unintended changes."""

    # Constants
    def test_nba_max_score_pinned(self):
        assert get_max_score("nba") == 44

    def test_nhl_max_score_pinned(self):
        assert get_max_score("nhl") == 25

    def test_cbb_max_score_pinned(self):
        assert get_max_score("cbb") == 38

    def test_cfb_max_score_pinned(self):
        assert get_max_score("cfb") == 35

    def test_mlb_max_score_pinned(self):
        assert get_max_score("mlb") == 25

    # Recommendations
    def test_nba_recommendation_pins(self):
        assert get_recommendation(12, "vegas", "nba") == "STRONG PLAY"
        assert get_recommendation(8, "vegas", "nba") == "CONFIDENT"
        assert get_recommendation(5, "vegas", "nba") == "LEAN"
        assert get_recommendation(2, "vegas", "nba") == "MONITOR"

    def test_nhl_recommendation_pins(self):
        assert get_recommendation(8, "vegas", "nhl") == "STRONG PLAY"
        assert get_recommendation(4, "vegas", "nhl") == "LEAN"
        assert get_recommendation(2, "vegas", "nhl") == "MONITOR"

    # Cover pct formula
    def test_cover_pct_formula_nba(self):
        """cover_pct = 50 + (score/max_score) * 45"""
        assert compute_raw_cover_pct(0, "nba") == 50.0
        assert compute_raw_cover_pct(44, "nba") == 95.0
        assert compute_raw_cover_pct(22, "nba") == 72.5

    def test_cover_pct_formula_nhl(self):
        assert compute_raw_cover_pct(0, "nhl") == 50.0
        assert compute_raw_cover_pct(25, "nhl") == 95.0

    # Line movement
    def test_movement_direction_pins(self):
        d, m = detect_movement(-5.5, -7.0)
        assert d == "public"
        assert m == pytest.approx(1.5)

        d, m = detect_movement(-5.5, -3.5)
        assert d == "vegas"
        assert m == pytest.approx(2.0)

    def test_movement_score_pins(self):
        # NBA scoring
        assert score_line_movement(0.5, "nba") == 0
        assert score_line_movement(1.5, "nba") == 2
        assert score_line_movement(2.5, "nba") == 3
        assert score_line_movement(3.5, "nba") == 5

        # Other sports
        assert score_line_movement(1.5, "nhl") == 3
        assert score_line_movement(2.5, "nhl") == 5
        assert score_line_movement(3.5, "nhl") == 8

    # Odds conversion
    def test_odds_conversion_pins(self):
        assert american_to_implied_prob(-110) == pytest.approx(0.5238, abs=0.001)
        assert american_to_implied_prob(150) == pytest.approx(0.40, abs=0.001)
        assert american_to_implied_prob(-200) == pytest.approx(0.6667, abs=0.001)
        assert american_to_implied_prob(100) == pytest.approx(0.50, abs=0.001)

    def test_decimal_payout_pins(self):
        assert american_to_decimal_payout(-110) == pytest.approx(1.909, abs=0.01)
        assert american_to_decimal_payout(150) == pytest.approx(2.50, abs=0.01)
        assert american_to_decimal_payout(100) == pytest.approx(2.00, abs=0.01)

    def test_vig_strip_pins(self):
        result = remove_vig(-110, -110)
        assert result["over_fair"] == pytest.approx(0.50, abs=0.01)
        assert result["vig_pct"] == pytest.approx(4.76, abs=0.5)

    # Elo math
    def test_expected_score_pins(self):
        assert _expected_score(1500, 1500) == pytest.approx(0.5)
        assert _expected_score(1900, 1500) == pytest.approx(0.909, abs=0.01)

    def test_mov_multiplier_pins(self):
        # Floor at 0.5
        assert _mov_multiplier(0, 0) == 0.5
        # Reasonable value for 10pt margin no gap
        mult = _mov_multiplier(10, 0)
        assert 1.0 < mult < 2.5

    # Model probability
    def test_model_probability_pins(self):
        result = compute_model_probability(25.5, 25.5, 5.0)
        assert result["prob_over"] == pytest.approx(0.5, abs=0.01)
        assert result["prob_under"] == pytest.approx(0.5, abs=0.01)

    def test_slot_confirmation_pins(self):
        assert confirms_slot("public", "public") is True
        assert confirms_slot("vegas", "vegas") is True
        assert confirms_slot("public", "vegas") is False
        assert confirms_slot("none", "public") is False
