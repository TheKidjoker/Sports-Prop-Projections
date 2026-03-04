# Joker's Edge

A rules-based sports betting analysis engine that evaluates spread plays across **NBA**, **NHL**, **CFB**, **CBB**, and **NFL**. Combines time-slot theory, line movement tracking, injury impact analysis, player prop projections, and sharp money detection to produce a confidence score for every game on the board.

Built with a dark red/black Gotham-themed UI. Scoring weights calibrated through historical backtesting (NHL validated out-of-sample at 67.3% accuracy, +28.5% ROI).

---

## Core Concept

Vegas adjusts its edge depending on when games are played and where the money flows. Every game is classified into a **public** or **vegas** slot, then layered with confirmation factors to build a composite score and cover percentage. The lean direction is sport-specific and backtested.

---

## Features

- **Auto Scanner** — Scans all games for a sport, ranks by confidence, surfaces picks above 68.5% cover
- **ALL Mode** — Scans all five sports simultaneously with cross-sport parlay suggestions
- **PRISM Player Props** (NBA) — Multi-stat projection engine for PTS, REB, AST using weighted averages, stat-specific matchup multipliers (opponent rebounds for REB, opponent steals for AST) with dynamic league averages, pace, rest, and usage redistribution
- **Pace Mismatch Detection** — Flags games with extreme pace gaps (5+ possessions NBA/CBB, 3+ NHL) using real possession estimates (FGA - OREB + TOV + 0.44*FTA), surfaced as orange badges with team names on game cards
- **Signal Freshness** — Cached scan results annotated with decay awareness (fresh/aging/stale) so users know when data may be outdated
- **Parlay Builder** — Auto-generated parlays: Two-Face's Safe Bet (2 legs, 80%+), Gotham Gambit (4-6 legs, 67.5%+), Gotham Breakout (4-10 legs, 60%+)
- **Joker's Lotto** — Cross-sport mega parlay from the best pick per sport
- **The Ledger** — Prediction tracker with auto-grading, win rate, CLV analysis, and Model Health dashboard
- **Bet Tracker** (Admin) — Personal bet slip to track placed spread bets and props, grade against outcomes, and view ROI dashboard
- **Rules Backtest Engine** — Replays scoring against historical outcomes to validate factor weights
- **EV Models** (NBA/NHL/CBB) — L2-regularized logistic regression that replaces heuristic scoring when validated
- **Calibration** — Logistic curve corrects raw scores to honest cover probabilities
- **Walk-Forward Validation** — Out-of-sample testing to detect overfitting
- **Slot Validation** — Statistical hypothesis testing (z-test, chi-squared, permutation test) for the public/vegas time slot theory
- **Advanced Team Stats** — Full ESPN team statistics integration (64 stats: efficiency, rebounding, steals, shooting splits, etc.)

---

## Architecture

```
app.py                Flask routes + API endpoints
game_scanner.py       Analysis engine — scans and scores all games
api_client.py         ESPN API integration
api_players.py        BallDontLie NBA player stats
api_odds.py           The-Odds-API spreads + player props
prism.py              Player prop projection engine
tracker.py            Prediction storage + grading + dashboard
bet_tracker.py        Admin bet slip — track, grade, dashboard
scan_cache.py         Background scan cache (instant page loads)
constants.py          Thresholds, max scores, signal decay classes, confidence registry
test_model/           Backtesting engine, EV models, walk-forward, slot validation
templates/index.html  Single-page app
static/               app.js + style.css (dark Gotham theme)
```

### Data Sources

ESPN (schedules, scores, spreads, injuries, stats, weather) | balldontlie.io (NBA player logs) | The-Odds-API (sharp money, prop lines) | OpenWeatherMap (NFL weather fallback)

---

## Quick Start

```bash
python app.py
```

Open `http://localhost:5000`. Click a sport card to auto-scan.

### Key Environment Variables

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_JWT_SECRET` | Authentication (empty = bypass) |
| `THE_ODDS_API_KEY` | Sharp money detection + posted prop lines |
| `OPENWEATHER_API_KEY` | NFL weather fallback |
| `ADMIN_EMAILS` | Comma-separated admin email allowlist |

---

## Validated Performance

| Sport | Out-of-Sample Accuracy | ROI | Status |
|-------|----------------------|-----|--------|
| NHL | 67.3% [61.8%-72.4%] | +28.5% | **Validated** |
| CBB | 49.1% | -6.3% | Overfit |
| NBA | 49.0% | -6.5% | Overfit |
| NFL | 34.5% (n=29) | -- | Insufficient data |

NHL is the only sport with confirmed out-of-sample performance. NBA/CBB weights are overfit to tuning data. See [README.md](README.md) for full backtest results, scoring tables, calibration details, and overfitting protection framework.
