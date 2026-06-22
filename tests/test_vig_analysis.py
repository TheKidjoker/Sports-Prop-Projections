"""Unit tests for vig_analysis.py (Phase 1) — vig stripping, shading detection."""

import pytest


class TestStripVig:
    @pytest.fixture(autouse=True)
    def setup(self):
        from vig_analysis import strip_vig, strip_vig_3way, detect_vig_shading, compute_market_width
        self.strip_vig = strip_vig
        self.strip_vig_3way = strip_vig_3way
        self.detect_vig_shading = detect_vig_shading
        self.compute_market_width = compute_market_width

    def test_standard_vig_proportional(self):
        """-110/-110 proportional strip = 50%/50%, ~4.76% vig."""
        result = self.strip_vig(-110, -110, method="proportional")
        assert result is not None
        assert result["home_fair"] == pytest.approx(0.50, abs=0.01)
        assert result["away_fair"] == pytest.approx(0.50, abs=0.01)
        assert result["overround"] == pytest.approx(4.76, abs=0.5)

    def test_asymmetric_vig(self):
        result = self.strip_vig(-200, 170, method="proportional")
        assert result is not None
        assert result["home_fair"] > result["away_fair"]
        assert result["home_fair"] + result["away_fair"] == pytest.approx(1.0, abs=0.001)

    def test_shin_method(self):
        """Shin's method should also produce valid probabilities."""
        result = self.strip_vig(-110, -110, method="shin")
        assert result is not None
        assert result["home_fair"] == pytest.approx(0.50, abs=0.02)
        assert result["overround"] > 0

    def test_3way_vig_strip(self):
        """Soccer 1X2 vig removal — probabilities should sum to 1.0."""
        result = self.strip_vig_3way(-120, 300, 280)
        assert result is not None
        total = result["home_fair"] + result["draw_fair"] + result["away_fair"]
        assert total == pytest.approx(1.0, abs=0.01)
        assert result["overround"] > 0

    def test_3way_home_favorite(self):
        """Home favorite in 1X2 should have highest fair prob."""
        result = self.strip_vig_3way(-200, 350, 500)
        assert result["home_fair"] > result["draw_fair"]
        assert result["home_fair"] > result["away_fair"]


class TestDetectVigShading:
    @pytest.fixture(autouse=True)
    def setup(self):
        from vig_analysis import detect_vig_shading
        self.detect_vig_shading = detect_vig_shading

    def test_no_shading(self):
        """Identical lines = no shading."""
        result = self.detect_vig_shading(
            pinnacle_line=-6.5, consensus_line=-6.5,
        )
        assert result["is_shaded"] is False

    def test_shading_detected(self):
        """Consensus shaded away from Pinnacle."""
        result = self.detect_vig_shading(
            pinnacle_line=-6.5, consensus_line=-7.5,
        )
        assert result["is_shaded"] is True
        assert result["shade_direction"] is not None

    def test_small_difference_no_shading(self):
        """0.5pt difference shouldn't flag shading."""
        result = self.detect_vig_shading(
            pinnacle_line=-6.5, consensus_line=-7.0,
        )
        assert result["is_shaded"] is False


class TestComputeMarketWidth:
    @pytest.fixture(autouse=True)
    def setup(self):
        from vig_analysis import compute_market_width
        self.compute_market_width = compute_market_width

    def test_single_line(self):
        result = self.compute_market_width([-6.5])
        assert result["width"] == 0.0

    def test_multiple_lines(self):
        result = self.compute_market_width([-6.5, -7.0, -6.0, -7.5])
        assert result["width"] == pytest.approx(1.5, abs=0.1)
        assert result["best"] == -6.0
        assert result["worst"] == -7.5

    def test_empty_lines(self):
        result = self.compute_market_width([])
        assert result["width"] == 0.0
