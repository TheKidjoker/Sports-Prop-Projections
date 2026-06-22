# ─── Soccer EV Model ─────────────────────────────────────────────────────────
# Multinomial logistic regression for 3-way soccer outcome prediction.
# Three-class output: home_win, draw, away_win.
# Walk-forward: 200-train / 50-test, step-50. AUC gate: 0.55 (one-vs-rest macro).

import math
import logging
import numpy as np

logger = logging.getLogger(__name__)

# League average xG for regression
_LEAGUE_AVG_XG = 1.35  # ~2.7 goals per game / 2 teams
_XG_REGRESSION_PRIOR = 10  # Regress toward mean after this many games


class SoccerEVModel:
    """
    Multinomial logistic regression for soccer match outcomes.
    Predicts P(home_win), P(draw), P(away_win).
    """

    FEATURE_NAMES = [
        "home_xg_regressed",
        "away_xg_regressed",
        "home_xga_regressed",
        "away_xga_regressed",
        "elo_diff",
        "home_form_5",
        "away_form_5",
        "h2h_goals_diff",
        "home_advantage_league",
        "match_importance",
    ]

    def __init__(self):
        self._model = None
        self._scaler = None
        self._is_trained = False
        self._metrics = {}

    def predict_probabilities(self, features):
        """
        Predict 3-way probabilities for a soccer match.

        Args:
            features: dict with FEATURE_NAMES keys

        Returns:
            dict with home_win, draw, away_win probabilities
        """
        if self._is_trained and self._model is not None:
            return self._predict_trained(features)
        return self._predict_heuristic(features)

    def _predict_heuristic(self, features):
        """
        Heuristic prediction when no trained model available.
        Uses xG differential and Elo to estimate probabilities.
        """
        home_xg = features.get("home_xg_regressed", _LEAGUE_AVG_XG)
        away_xg = features.get("away_xg_regressed", _LEAGUE_AVG_XG)
        elo_diff = features.get("elo_diff", 0)
        home_adv = features.get("home_advantage_league", 0.45)

        # xG-based strength estimate
        xg_diff = home_xg - away_xg
        xg_signal = xg_diff * 0.15  # Scale down

        # Elo-based signal
        elo_signal = elo_diff / 400.0 * 0.3  # Normalized

        # Combined home advantage
        raw_home_strength = 0.5 + xg_signal + elo_signal + (home_adv - 0.45) * 0.5

        # Clip to reasonable range
        raw_home_strength = max(0.15, min(0.85, raw_home_strength))

        # Draw probability model
        closeness = 1.0 - abs(raw_home_strength - 0.5) * 2
        draw_base = 0.22
        draw_range = 0.12
        draw_prob = draw_base + draw_range * closeness

        # Distribute remaining
        remaining = 1.0 - draw_prob
        home_prob = remaining * raw_home_strength
        away_prob = remaining * (1.0 - raw_home_strength)

        # Normalize to ensure sum = 1.0
        total = home_prob + draw_prob + away_prob
        return {
            "home_win": round(home_prob / total, 4),
            "draw": round(draw_prob / total, 4),
            "away_win": round(away_prob / total, 4),
        }

    def _predict_trained(self, features):
        """Predict using trained sklearn model."""
        try:
            X = np.array([[features.get(f, 0) for f in self.FEATURE_NAMES]])
            if self._scaler is not None:
                X = self._scaler.transform(X)
            probs = self._model.predict_proba(X)[0]
            classes = self._model.classes_
            result = {}
            class_map = {0: "home_win", 1: "draw", 2: "away_win"}
            for i, cls in enumerate(classes):
                result[class_map.get(cls, f"class_{cls}")] = round(float(probs[i]), 4)
            # Ensure all keys present
            for key in ("home_win", "draw", "away_win"):
                result.setdefault(key, 0.0)
            return result
        except Exception as e:
            logger.warning("[soccer_ev] Trained prediction failed: %s", e)
            return self._predict_heuristic(features)

    def train(self, training_data):
        """
        Train multinomial logistic regression.

        Args:
            training_data: list of dicts with FEATURE_NAMES + "outcome" (0=home, 1=draw, 2=away)

        Returns:
            dict with metrics (auc, accuracy, etc.)
        """
        if not training_data or len(training_data) < 100:
            return {"error": "insufficient_data", "sample_size": len(training_data or [])}

        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler
            from sklearn.metrics import roc_auc_score

            X = np.array([[d.get(f, 0) for f in self.FEATURE_NAMES] for d in training_data])
            y = np.array([d["outcome"] for d in training_data])

            # Chronological split (70/30)
            split = int(len(X) * 0.70)
            X_train, X_test = X[:split], X[split:]
            y_train, y_test = y[:split], y[split:]

            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_test_s = scaler.transform(X_test)

            model = LogisticRegression(
                multi_class="multinomial",
                penalty="l2",
                C=0.05,
                max_iter=1000,
                solver="lbfgs",
            )
            model.fit(X_train_s, y_train)

            # Evaluate
            probs = model.predict_proba(X_test_s)
            try:
                auc = roc_auc_score(y_test, probs, multi_class="ovr", average="macro")
            except Exception:
                auc = 0.0

            accuracy = model.score(X_test_s, y_test)

            self._model = model
            self._scaler = scaler
            self._is_trained = auc >= 0.55  # AUC gate

            self._metrics = {
                "auc": round(float(auc), 4),
                "accuracy": round(float(accuracy) * 100, 1),
                "train_size": len(X_train),
                "test_size": len(X_test),
                "activated": self._is_trained,
            }
            return self._metrics

        except Exception as e:
            logger.error("[soccer_ev] Training failed: %s", e)
            return {"error": str(e)}

    def regress_xg(self, raw_xg, games_played=10):
        """
        Regress xG toward league average using Bayesian shrinkage.
        More games = more weight on actual performance.

        Args:
            raw_xg: team's raw xG per game
            games_played: number of games in sample

        Returns:
            regressed xG value
        """
        prior_weight = _XG_REGRESSION_PRIOR
        regressed = (
            (raw_xg * games_played + _LEAGUE_AVG_XG * prior_weight)
            / (games_played + prior_weight)
        )
        return round(regressed, 3)

    @property
    def metrics(self):
        return self._metrics

    @property
    def is_active(self):
        return self._is_trained
