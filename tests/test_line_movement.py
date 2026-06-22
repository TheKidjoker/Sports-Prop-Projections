"""Unit tests for line_movement.py — spread movement detection, slot confirmation, scoring."""

import pytest
from line_movement import detect_movement, confirms_slot, score_line_movement, _parse_spread


class TestParseSpread:
    def test_none_returns_none(self):
        assert _parse_spread(None) is None

    def test_float_passthrough(self):
        assert _parse_spread(-6.5) == -6.5

    def test_int_to_float(self):
        assert _parse_spread(3) == 3.0

    def test_string_positive(self):
        assert _parse_spread("+4.5") == 4.5

    def test_string_negative(self):
        assert _parse_spread("-6") == -6.0

    def test_string_no_sign(self):
        assert _parse_spread("4.5") == 4.5

    def test_string_whitespace(self):
        assert _parse_spread("  -3.5  ") == -3.5

    def test_invalid_string(self):
        assert _parse_spread("pick") is None

    def test_empty_string(self):
        assert _parse_spread("") is None


class TestDetectMovement:
    def test_none_opening(self):
        direction, mag = detect_movement(None, -6.5)
        assert direction == "none"
        assert mag == 0.0

    def test_none_current(self):
        direction, mag = detect_movement(-5.5, None)
        assert direction == "none"
        assert mag == 0.0

    def test_both_none(self):
        direction, mag = detect_movement(None, None)
        assert direction == "none"
        assert mag == 0.0

    def test_no_movement(self):
        direction, mag = detect_movement(-5.5, -5.5)
        assert direction == "none"
        assert mag == 0.0

    def test_public_movement(self):
        """More negative current = public money pushing the line."""
        direction, mag = detect_movement(-5.5, -7.0)
        assert direction == "public"
        assert mag == pytest.approx(1.5)

    def test_vegas_movement(self):
        """More positive current = sharp/Vegas money."""
        direction, mag = detect_movement(-5.5, -3.5)
        assert direction == "vegas"
        assert mag == pytest.approx(2.0)

    def test_string_inputs(self):
        direction, mag = detect_movement("+4.5", "+1.5")
        assert direction == "public"
        assert mag == pytest.approx(3.0)

    def test_negative_spread_to_positive(self):
        """Spread flips from home-fav to away-fav."""
        direction, mag = detect_movement(-1.0, 2.0)
        assert direction == "vegas"
        assert mag == pytest.approx(3.0)

    def test_zero_movement_float(self):
        direction, mag = detect_movement(0.0, 0.0)
        assert direction == "none"
        assert mag == 0.0


class TestConfirmsSlot:
    def test_public_public(self):
        assert confirms_slot("public", "public") is True

    def test_vegas_vegas(self):
        assert confirms_slot("vegas", "vegas") is True

    def test_public_vegas(self):
        assert confirms_slot("public", "vegas") is False

    def test_vegas_public(self):
        assert confirms_slot("vegas", "public") is False

    def test_none_public(self):
        assert confirms_slot("none", "public") is False

    def test_none_vegas(self):
        assert confirms_slot("none", "vegas") is False

    def test_public_unknown(self):
        assert confirms_slot("public", "unknown") is False

    def test_vegas_unknown(self):
        assert confirms_slot("vegas", "unknown") is False

    def test_none_none(self):
        assert confirms_slot("none", "none") is False


class TestScoreLineMovement:
    # NBA-specific scoring
    def test_nba_under_1(self):
        assert score_line_movement(0.5, "nba") == 0

    def test_nba_at_1(self):
        assert score_line_movement(1.0, "nba") == 2

    def test_nba_1_to_2(self):
        assert score_line_movement(1.5, "nba") == 2

    def test_nba_at_2(self):
        assert score_line_movement(2.0, "nba") == 3

    def test_nba_2_to_3(self):
        assert score_line_movement(2.5, "nba") == 3

    def test_nba_at_3(self):
        assert score_line_movement(3.0, "nba") == 5

    def test_nba_above_3(self):
        assert score_line_movement(5.0, "nba") == 5

    def test_nba_zero(self):
        assert score_line_movement(0.0, "nba") == 0

    # Other sports scoring
    def test_nhl_under_1(self):
        assert score_line_movement(0.5, "nhl") == 0

    def test_nhl_1_to_2(self):
        assert score_line_movement(1.5, "nhl") == 3

    def test_nhl_2_to_3(self):
        assert score_line_movement(2.5, "nhl") == 5

    def test_nhl_above_3(self):
        assert score_line_movement(4.0, "nhl") == 8

    def test_cfb_boundary(self):
        assert score_line_movement(1.0, "cfb") == 3

    def test_default_sport(self):
        """Default sport should use non-NBA scoring."""
        assert score_line_movement(3.0) == 5  # default is "nba"

    def test_zero_magnitude(self):
        assert score_line_movement(0, "nba") == 0
        assert score_line_movement(0, "nhl") == 0
