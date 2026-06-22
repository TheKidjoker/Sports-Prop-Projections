"""Unit tests for soccer_ev_model.py (Phase 3) — multinomial logistic, 3-way output."""

import pytest


class TestSoccerEVModel:
    @pytest.fixture(autouse=True)
    def setup(self):
        from soccer_ev_model import SoccerEVModel
        self.model = SoccerEVModel()

    def test_predict_probabilities_sum_to_1(self):
        """Three-way probabilities must sum to 1.0."""
        features = {
            "home_xg_regressed": 1.8,
            "away_xg_regressed": 1.3,
            "home_xga_regressed": 0.9,
            "away_xga_regressed": 1.1,
            "elo_diff": 50,
            "home_form_5": 0.8,
            "away_form_5": 0.6,
            "h2h_goals_diff": 0.5,
            "home_advantage_league": 0.46,
            "match_importance": 0.8,
        }
        probs = self.model.predict_probabilities(features)
        assert probs is not None
        assert "home_win" in probs
        assert "draw" in probs
        assert "away_win" in probs
        total = probs["home_win"] + probs["draw"] + probs["away_win"]
        assert total == pytest.approx(1.0, abs=0.01)

    def test_all_probabilities_non_negative(self):
        features = {
            "home_xg_regressed": 1.0,
            "away_xg_regressed": 1.0,
            "home_xga_regressed": 1.0,
            "away_xga_regressed": 1.0,
            "elo_diff": 0,
            "home_form_5": 0.5,
            "away_form_5": 0.5,
            "h2h_goals_diff": 0.0,
            "home_advantage_league": 0.45,
            "match_importance": 0.5,
        }
        probs = self.model.predict_probabilities(features)
        assert probs["home_win"] >= 0
        assert probs["draw"] >= 0
        assert probs["away_win"] >= 0

    def test_home_advantage_shifts_probability(self):
        """Strong home team should have higher home_win probability."""
        strong_home = {
            "home_xg_regressed": 2.5,
            "away_xg_regressed": 0.8,
            "home_xga_regressed": 0.7,
            "away_xga_regressed": 1.5,
            "elo_diff": 200,
            "home_form_5": 0.9,
            "away_form_5": 0.3,
            "h2h_goals_diff": 1.5,
            "home_advantage_league": 0.50,
            "match_importance": 0.7,
        }
        probs = self.model.predict_probabilities(strong_home)
        assert probs["home_win"] > probs["away_win"]

    def test_draw_probability_reasonable(self):
        """Draw probability should be in a reasonable range for soccer."""
        features = {
            "home_xg_regressed": 1.2,
            "away_xg_regressed": 1.2,
            "home_xga_regressed": 1.0,
            "away_xga_regressed": 1.0,
            "elo_diff": 20,
            "home_form_5": 0.5,
            "away_form_5": 0.5,
            "h2h_goals_diff": 0.0,
            "home_advantage_league": 0.45,
            "match_importance": 0.5,
        }
        probs = self.model.predict_probabilities(features)
        # Draws happen ~20-30% in soccer
        assert 0.15 < probs["draw"] < 0.45

    def test_feature_names(self):
        assert len(self.model.FEATURE_NAMES) == 10
        assert "elo_diff" in self.model.FEATURE_NAMES
        assert "home_xg_regressed" in self.model.FEATURE_NAMES

    def test_xg_feature_engineering(self):
        """xG regression should blend toward league average."""
        raw_xg = 3.0  # Unusually high
        regressed = self.model.regress_xg(raw_xg, games_played=5)
        assert regressed < raw_xg  # Should be pulled toward mean
        assert regressed > 1.0  # But still elevated
