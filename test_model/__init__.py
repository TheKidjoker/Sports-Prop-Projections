"""
Test Model — ML-based backtest and prediction overlay for Joker's Edge.

Validates whether historical pattern alignment produces a sustainable
predictive edge against the market by training a GradientBoostingClassifier
on retroactively-computed features and comparing its probabilities to
closing line implied probabilities.
"""
