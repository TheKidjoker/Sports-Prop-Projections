"""Unit tests for calibration.py — raw cover_pct, calibration compute, logistic/isotonic fit."""

import pytest
import numpy as np
from calibration import (
    compute_raw_cover_pct, compute_calibration, load_calibration,
    get_calibrated_cover_pct, is_loaded, _calibration_cache,
)


class TestComputeRawCoverPct:
    def test_zero_score(self):
        """Score 0 should give 50% (coin flip)."""
        assert compute_raw_cover_pct(0, "nba") == 50.0

    def test_max_score_nba(self):
        """Max score should give 95% (50 + 45)."""
        result = compute_raw_cover_pct(44, "nba")
        assert result == 95.0

    def test_max_score_nhl(self):
        result = compute_raw_cover_pct(25, "nhl")
        assert result == 95.0

    def test_half_score(self):
        """Half of max should give ~72.5%."""
        result = compute_raw_cover_pct(22, "nba")
        assert result == pytest.approx(72.5, abs=0.5)

    def test_negative_score(self):
        """Negative score should give < 50%."""
        result = compute_raw_cover_pct(-5, "nba")
        assert result < 50.0

    def test_each_sport(self):
        """All sports should follow the same formula."""
        for sport, max_s in [("nba", 44), ("nhl", 25), ("cbb", 38), ("nfl", 35), ("mlb", 25)]:
            result = compute_raw_cover_pct(max_s, sport)
            assert result == pytest.approx(95.0, abs=0.1), f"{sport} max score failed"


class TestComputeCalibration:
    def test_empty_predictions(self):
        result = compute_calibration([], "nba")
        assert result["brier_score"] is None
        assert result["sample_size"] == 0
        assert result["adjustment_needed"] is False

    def test_basic_calibration(self):
        """With enough predictions, should compute valid calibration metrics."""
        predictions = []
        for i in range(100):
            score = (i % 20) + 5
            # Higher scores more likely correct
            correct = score > 12
            predictions.append({"score": score, "correct": correct})

        result = compute_calibration(predictions, "nba")
        assert result["brier_score"] is not None
        assert 0 <= result["brier_score"] <= 1.0
        assert result["sample_size"] == 100
        assert result["ece"] is not None

    def test_perfect_predictions(self):
        """All correct at high scores should have low Brier."""
        predictions = [{"score": 30, "correct": True} for _ in range(60)]
        result = compute_calibration(predictions, "nba")
        assert result["brier_score"] is not None
        # Brier should be relatively low (predictions match outcomes)
        assert result["brier_score"] < 0.5

    def test_bins_structure(self):
        predictions = [{"score": i * 2, "correct": i % 2 == 0} for i in range(60)]
        result = compute_calibration(predictions, "nba")
        assert isinstance(result["bins"], list)
        if result["bins"]:
            for b in result["bins"]:
                assert "range" in b
                assert "count" in b
                assert "avg_predicted" in b
                assert "actual_rate" in b


class TestCalibrationCache:
    def setup_method(self):
        """Clear calibration cache before each test."""
        _calibration_cache.clear()

    def test_load_logistic(self):
        params = {
            "logistic_params": {
                "base": 0.45, "amplitude": 0.35,
                "k": 0.15, "midpoint": 15.0, "max_score": 44,
            },
            "sample_size": 500,
        }
        load_calibration("nba", params)
        assert is_loaded("nba")

    def test_load_none(self):
        load_calibration("nba", None)
        assert not is_loaded("nba")

    def test_get_calibrated_no_model(self):
        result = get_calibrated_cover_pct(10, "nba")
        assert result is None

    def test_get_calibrated_with_logistic(self):
        params = {
            "logistic_params": {
                "base": 0.45, "amplitude": 0.35,
                "k": 0.15, "midpoint": 15.0, "max_score": 44,
            },
            "sample_size": 500,
        }
        load_calibration("nba", params)
        result = get_calibrated_cover_pct(20, "nba")
        assert result is not None
        assert 0 < result < 100

    def test_isotonic_small_sample_rejected(self):
        """Isotonic with small sample should be rejected."""
        params = {
            "isotonic_breakpoints": {"x": [50, 60, 70], "y": [48, 58, 68]},
            "sample_size": 50,
        }
        load_calibration("test_sport", params)
        assert not is_loaded("test_sport")

    def test_isotonic_large_sample_accepted(self):
        params = {
            "isotonic_breakpoints": {"x": [50, 60, 70, 80], "y": [48, 58, 68, 78]},
            "sample_size": 300,
        }
        load_calibration("test_sport", params)
        assert is_loaded("test_sport")
