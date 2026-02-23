# Future Ideas

Planned features and enhancements for Joker's Edge.

---

## 1. Player Props in Quick Pick Generate

When clicking **Get Picks**, include player prop recommendations alongside the game-level spread picks. Each player prop should display:

- **Player name and team**
- **Category** (Points, Rebounds, Assists, 3-Pointers, Blocks, Steals, etc.)
- **PRISM projection vs posted line**
- **Signal** (STRONG OVER, LEAN UNDER, etc.)
- **Confidence %**

The parlay builder (Two-Face's Safe Bet, Gotham Gambit, Gotham Breakout) should also be able to mix spread picks with player props for combo parlays.

---

## 2. User Accounts and Database

Set up a database for user authentication so people can sign in and sign out. Features:

- **Registration and login** (email/password or social login)
- **Personal dashboard** — each user sees their own pick history, win rate, and ledger
- **Saved preferences** — favorite sports, notification settings, bankroll tracking
- **Session management** — stay logged in across devices, secure sign out

---

## 3. Custom Logos on Startup

Add custom Joker's Edge branding logos to the welcome hero and loading screens:

- **Animated logo** on the welcome hero landing page
- **Loading spinner replacement** — swap the generic spinner for a branded Joker's Edge animation
- **Favicon and app icons** — custom icon for browser tabs and mobile home screen
- **Sport-specific logo variants** — different logo treatments per sport card on the hero page

---

## 4. Expand PRISM Categories

Add rebounds, assists, and 3-pointers to PRISM projections — not just points. Multiply the number of prop signals per game with adjusted thresholds for each stat type.

---

## 5. Schedule Spot Analysis

Detect trap, letdown, and look-ahead situations using existing schedule data:

- **Letdown** — coming off a big win, now facing a weaker opponent (regression risk)
- **Look-ahead** — easy game today but a top team next game (starters may coast)
- **Revenge 2.0** — second meeting after losing game 1 of a back-to-back series

---

## 6. Travel and Time Zone Fatigue

Flag games where a West coast team plays an early East coast tip-off (e.g. 7 PM EST = 4 PM body clock). Use existing venue city/state data to detect cross-country travel fatigue.

---

## 7. Pace-of-Play Matchup

Pull each team's pace (possessions per game) and flag extreme matchups. Two fast teams = over lean, two slow teams = under lean. Goes beyond just the raw O/U total.

---

## 8. Referee Tendencies (NBA)

Certain ref crews call more fouls — more free throws = higher scoring. Impacts overs and player point props. ESPN sometimes exposes officials in the game summary data.

---

## 9. Seasonal Context Flags

Detect situational edges based on where teams are in the season:

- **Post All-Star break** performance shifts
- **End-of-season tank** detection (teams with nothing to play for)
- **Playoff push urgency** (teams fighting for seeding in final 15 games)
- **Back from long break** (rust factor after 3+ days off)

---

## 10. Division Rivalry Tightener

Divisional games tend to be closer regardless of talent gap. If two division rivals play and the spread is large, apply a discount — these games stay tighter than the number suggests.

---

## 11. Historical Backtesting Engine

Validate the entire model against 5+ years of historical data with walk-forward testing. Every weight, threshold, and bonus in the system is currently hardcoded with no evidence of positive expected value. Build a pipeline that:

- Collects historical games, spreads, injuries, and results
- Replays the algorithm on past games as if predicting live
- Measures ROI, hit rate, and Brier score per factor and overall
- Uses holdout/out-of-sample sets to detect overfitting
- Reports CLV (Closing Line Value) — the gold standard for sharp betting

Without this, the model is an untested hypothesis.

---

## 12. Weight Optimization (Replace Hardcoded Thresholds)

Every scoring weight is arbitrary right now — Trell Rule +5, B2B +4, line movement 3/5/8 by tier, public slot +10 confidence. Replace with data-driven weights:

- Use logistic regression or gradient descent to learn optimal factor weights from historical outcomes
- Apply L1/L2 regularization to prevent overfitting across the 15+ features
- PCA / dimensionality reduction — consolidate correlated factors (line movement + slot type + public betting % often measure the same signal) into 3-5 uncorrelated components
- Separate weight sets per sport — don't assume NBA weights work for NFL or CFB

---

## 13. Fix Probability Math

The current probability model in `projections.py` has scaling artifacts:

```python
probability = 0.5 + (difference / vegas_line)
```

A 5-point miss on a 40-point line = 12.5% swing, but the same miss on a 10-point line = 50% swing. Replace with:

- Logistic regression or calibrated probability distributions
- Proper Bayesian updating instead of linear scaling
- Cover % conversion should floor below breakeven (52.4% at -110 juice), not at 50%

---

## 14. Vig-Adjusted Breakeven Thresholds

The system treats 50% as breakeven. At standard -110 juice, you need 52.4% to profit. All confidence thresholds, take/pass decisions, and parlay recommendations should account for this. Marginal "take" calls at 51-52% are actually -EV after juice.

---

## 15. Decorrelate Scoring Factors

The additive scoring assumes each factor is independent. They're not:

- Line movement + slot type + public betting % often measure the same underlying signal
- ATS record + home/away split + spread magnitude are correlated
- Stacking correlated factors inflates confidence without adding real information

Fix: measure factor correlations on historical data, apply PCA or partial correlation, and discount redundant signals.

---

## 16. Closing Line Value (CLV) Tracking

Track the line at game time vs. when the pick was made. CLV is the strongest predictor of long-term betting profitability. If the model consistently beats the closing line, it has real edge. If not, the win rate is luck.

---

## 17. Kelly Criterion Position Sizing

All recommendations are currently binary (take/pass). Add bet sizing based on edge magnitude:

- Kelly fraction = (edge / odds) for optimal bankroll growth
- Fractional Kelly (quarter or half) for safety
- A 90% confidence pick should get a larger allocation than a 60% pick
- Bankroll tracking and drawdown limits

---

## 18. Quantify Injury Impact

The Trell Rule assigns a flat +5 regardless of context. Improve by:

- Scaling impact by player usage rate / minutes share
- Checking if the spread already moved for the injury (if line moved 3+ pts post-announcement, edge is priced in)
- Factoring in backup quality (depth chart data)
- Distinguishing "LeBron out" from a borderline starter going down

---

## 19. Signal Decay Awareness

Most signals lose value before you can act on them:

- Line movement: by the time it's visible, the edge is often gone
- Public betting %: books adjust in real-time
- Injury news: lines move within minutes of announcement

Add timestamps to each signal and discount stale ones. Prefer signals with slower decay (schedule spots, rest advantages, matchup mismatches) over fast-decay signals (line movement, public %).

---

## 20. Advanced Stats Integration

The model lacks modern efficiency metrics. Add:

- Four Factors (eFG%, TOV%, OREB%, FT rate) for basketball
- True Shooting % and pace-adjusted ratings
- Expected Points Added (EPA) for NFL
- Team strength ratings independent of spreads (Elo, power ratings)
- Per-position defensive stats instead of just total points allowed

---

## 21. PRISM Matchup Fix for Rebounds/Assists

PRISM currently uses "points allowed" as a matchup multiplier for all stat categories. This is invalid for rebounds (pace matters more than opponent defense) and assists (opponent turnover rate matters more). Use stat-specific defensive metrics:

- Rebounds: opponent pace + offensive rebound rate allowed
- Assists: opponent turnover forcing rate + perimeter defense rating
- Points: keep current defensive rating approach

---

## 22. Validate Time Slot Hypothesis

The entire system hinges on "public money dominates certain time slots, sharp money others." This is popular in betting communities but unproven. Need to:

- Test whether slot classification actually predicts ATS outcomes historically
- Measure if public-slot fades and vegas-slot leans have statistically significant edge
- Compare against null hypothesis (random slot assignment)
- If slots don't predict outcomes, the model's foundation needs rethinking

---
