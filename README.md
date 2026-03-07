# Joker's Edge

A rules-based sports betting analysis engine that evaluates spread plays across **NBA**, **NHL**, **CFB**, **CBB**, and **NFL**. Combines time-slot theory, line movement tracking, injury impact analysis, player prop projections (PRISM), EV modeling, sharp money detection, and sport-specific intelligence signals to produce a confidence score for every game on the board.

All scoring weights have been calibrated through historical backtesting against real outcomes (NBA: 607 games, NHL: 529, CBB: 1,977, NFL: 105, CFB: 51). NHL is the only sport with validated out-of-sample performance (67.3% accuracy, +28.5% ROI).

Features a React + Vite frontend with dark red/black Gotham-themed UI ("Joker's Edge"), PRISM player prop projections for NBA/NHL/CBB, variance-based Prop EV engine, personal bet tracker with auto-grading, and an instant-load background scan cache system.

---

## Core Theory

Not all time slots are created equal. Vegas adjusts its edge depending on when games are played, who's watching, and where the money flows. This tool classifies every game into a **slot type** (public or vegas), then layers confirmation factors on top to build a composite score and cover percentage.

- **Public slots** produce sensible, chalk outcomes.
- **Vegas slots** are where the books hold the edge and sharp money dominates.

The lean direction is **sport-specific** (see Lean Logic below).

---

## How Scoring Works

Each game starts at a base of 50% cover probability. Confirmation factors add points to a composite score, which maps to a cover percentage via sport-specific logistic calibration (where available) or a linear fallback:

```
Logistic:  cover_pct = L + K / (1 + exp(-r * (score - x0)))    (NHL, NBA, CBB)
Linear:    cover_pct = 50 + (score / max_score) * 45            (NFL, CFB fallback)
```

NHL example: `cover% = 65.3 + 16.8 / (1 + exp(-2.0 * (score - 7.68)))`

### Scoring Factors (Backtested)

Weights are sport-specific. The table shows the default value and sport overrides where applicable.

| Factor | Default | NBA V6 | NHL V3 | CBB V4 | NFL V1 | Applies To |
|--------|---------|--------|--------|--------|--------|------------|
| Public slot bonus | +3 | +2 | +3 | +3 | +3 | All |
| Line movement confirms slot | +3/+5/+8 | +2/+3/+5 | default | default | default | All (graduated) |
| Line direction toward dog | -- | +2 | -- | -- | +3 | NBA, NFL |
| Line direction toward fav | -- | -1 | -- | -- | -2 | NBA, NFL |
| Trell Rule (star injury) | +5 | +5 | +5 | +5 | +5 | All |
| Rank Scam detected | +5 | -- | -- | +5 | -- | CFB, CBB |
| Spread Discrepancy | +5 | -- | -- | +5 | -- | CFB, CBB |
| Trend Discrepancy | -- | -- | -- | -- | +5 | NFL |
| O/U Discrepancy | -- | -- | -- | -- | +5 | NFL |
| Weather factor | -- | -- | -- | -- | +5 | NFL |
| B2B rest advantage | +2 | +2 | +2 | -- | -- | NBA, NHL |
| B2B fatigue penalty | -1 | -1 | -1 | -- | -- | NBA, NHL |
| ATS record bonus (>60%) | +2 | +2 | +2 | **0** | +2 | All |
| ATS record penalty (<40%) | **0** | **0** | **0** | **+2** | **0** | All |
| Home/away split | **0** | **0** | **0** | **0** | **0** | All |
| Sharp money divergence | +5 | +5 | +5 | +5 | +5 | Vegas slots |
| Sharp + public alignment | +3 | +3 | +3 | +3 | +3 | Public slots |
| H2H revenge bonus | **0** | **0** | **0** | **0** | **0** | All |
| H2H dominance bonus | **0** | **0** | **0** | **0** | **0** | All |
| Vegas Trap (cold favorite) | -- | +5/+7 | -- | -- | -- | NBA |
| Feedback loop | -2 to +3 | same | same | same | same | All |
| Tuesday penalty | -- | **-3** | -- | -- | -- | NBA |
| Sunday penalty | -- | -- | -- | **-4** | -- | CBB |
| Friday penalty | -- | -- | **-3** | -- | -- | NHL |
| Spread sweet spot | -- | +2 (3-5) | -- | +3 (6-10) | +3 (3-7) | NBA, CBB, NFL |
| Spread death zone | -- | -3 (5-7) | -- | -3 (<3) | -3 (<3) | NBA, CBB, NFL |
| Spread blowout penalty | -3 | -3 (13+) | -- | -2 (15+) | -3 (10+) | All |

**Bold** = backtested change from default. **0** = factor removed (backtested as harmful/noise).

### Max Scores by Sport

| Sport | Max Score |
|-------|-----------|
| NBA | 31 |
| NHL | 25 |
| CBB | 38 |
| CFB | 35 |
| NFL | 35 |

Games scoring 68.5%+ cover are surfaced as picks. Below that, the top 5 closest games are shown as alternatives. Games between 58-68.5% appear as "Other Games to Watch."

### Recommendation Thresholds (Backtested)

Thresholds are sport-specific and, for NBA/NHL, slot-specific:

**NBA** (3-tier with CONFIDENT):
| Slot | STRONG PLAY | CONFIDENT | LEAN | MONITOR |
|------|-------------|-----------|------|---------|
| Vegas | >= 7 | >= 5 | >= 4 | < 4 |
| Public | >= 7 | -- | >= 5 | < 5 |

**NHL** (public capped at LEAN):
| Slot | STRONG PLAY | LEAN | MONITOR |
|------|-------------|------|---------|
| Vegas | >= 7 | >= 3 | < 3 |
| Public | -- | >= 5 | < 5 |

**CBB / CFB / NFL** (flat thresholds):
| Sport | STRONG PLAY | LEAN | MONITOR |
|-------|-------------|------|---------|
| CBB | >= 13 | >= 10 | < 10 |
| CFB | >= 11 | >= 9 | < 9 |
| NFL | >= 15 | >= 8 | < 8 |

### Line Movement Scoring (Graduated)

| Movement | Default | NBA |
|----------|---------|-----|
| 0-1 pts | 0 | 0 |
| 1-2 pts | 3 | 2 |
| 2-3 pts | 5 | 3 |
| 3+ pts | 8 | 5 |

---

## Lean Logic (Backtested)

The lean direction is **not** one-size-fits-all. Backtesting revealed different patterns per sport:

| Sport | Public Slots | Vegas Slots | Notes |
|-------|-------------|-------------|-------|
| **NBA** | Underdog | Underdog | Always lean underdog — public inflates favorite lines |
| **NHL** | Underdog | Underdog | Always lean underdog — favorite lean was 37.5%, underdog 71.2% |
| **CBB** | Favorite | Underdog | Standard public/vegas theory |
| **CFB** | Favorite | Underdog | Standard public/vegas theory |
| **NFL** | **Underdog** | **Favorite** | Opposite of other sports — NFL public money inflates favorites differently |

The action string includes the spread value and a "don't take past" limit (spread minus 1.5 points). When the spread exceeds the sport-specific moneyline threshold, the tool recommends taking the moneyline instead.

| Sport | ML Threshold |
|-------|-------------|
| NBA | 6+ points |
| NFL | 3+ points |
| CFB | 7+ points |
| CBB | 7+ points |

### Trell Rule Lean Override
When the Trell Rule fires (star player recently injured + out + vegas slot), the lean overrides to the star's team — the market overreacts to star injuries and creates value.

---

## Sports Supported

### NBA
- **Timezone:** PST (UTC-8) for slot classification, EST for display
- **Slot rules:** Day-of-week determines the slot schedule. Mon/Wed/Fri = public days, Tue/Thu/Sat/Sun = vegas days. Alternating public/vegas slots at specific tip-off times. 30-min tolerance for classification.
- **First-game override:** The first game of the day gets the opposite slot of the day type.
- **Player props (PRISM):** Multi-stat projection engine for PTS, REB, AST on top 3 scorers per team (see PRISM section below).
- **Vegas Trap:** Detects heavy favorites (7+ pt spread) on cold streaks in vegas slots. +5 if favorite is cold (0-2 wins in last 7), +7 if both teams are cold.
- **Line direction:** +2 when line moves toward underdog, -1 toward favorite.
- **Tuesday penalty:** -3 (40.8% dog cover — worst day).
- **Spread sweet spot:** +2 for 3-4.5pt spreads (57.1%), -3 for 5-6.5 (death zone, 47.6%), -3 for 13+ (blowout, 46.0%).
- **B2B:** +2 bonus, -1 penalty.
- **H2H/Home-away:** Removed (backtested as noise).
- **Moneyline threshold:** 6+ point spreads recommend ML instead of spread.

### NHL
- **Timezone:** CST (UTC-6) for slot classification, EST for display
- **Slot rules:** NBA-style framework based on day type + slate size + time:
  - Public days: Mon/Thu/Fri | Vegas days: Tue/Wed/Sat/Sun
  - 1 game = vegas, 2 games = first public / second vegas
  - 3+ games = first game opposite of day type, rest time-based
  - Time slots (CST): 12pm=public, 2pm=vegas, 4pm=public, 6pm=public, 7pm=vegas, 8pm=public, 9pm=vegas
  - 60-min tolerance for classification (0% unknown, was 65% unknown)
- **Player props (PRISM):** Multi-stat projection engine for PTS (points), GOALS, AST (assists), SOG (shots on goal) on top 3 scorers per team.
- **All spreads are ±1.5** (puck line) — no spread adjustment possible.
- **Friday penalty:** -3 (57.5% dog cover, Fri_public only 46.2%).
- **ATS/B2B/H2H/Home-away:** Removed (backtested as noise or harmful).
- **Moneyline:** Not used (puck line sport).

### CFB (College Football)
- **Timezone:** EST (UTC-5) for both classification and display
- **Slot rules:** Day overrides (Thu/Fri = public, Mon = trap, Sun = public) + Saturday time-based slots
- **Rank Scam:** Detects when a higher-ranked team is at home but listed as the underdog. In public slots, the ranked home underdog is expected to cover. In vegas slots, fade them.
- **Spread Discrepancy:** Flags games where the actual spread is significantly below the expected range for a ranked team's tier vs an unranked opponent.
- **Rank tiers:**
  - Frontend (#1-9): Public darlings, don't expect big spread covers
  - Middle (#10-19): Case by case
  - Backend (#20-25): Under the radar, expected to cover
- **Expected spread ranges (ranked vs unranked):**
  | Rank | Expected Spread |
  |------|----------------|
  | #1-5 | 24-28 pts |
  | #6-10 | 18-22 pts |
  | #11-15 | 14-18 pts |
  | #16-20 | 10-14 pts |
  | #21-25 | 7-10 pts |
- **Moneyline threshold:** 7+ points (touchdown margin).

### CBB (College Basketball)
- **Timezone:** EST (UTC-5) for both classification and display
- **Slot rules:** Day overrides (Mon/Tue = vegas/sharp, Wed-Fri = public, Sun = public) + Saturday time-based slots with 60-min tolerance
- **Rank Scam + Spread Discrepancy:** Same logic as CFB with basketball-calibrated expected spreads (~half of CFB ranges).
- **Expected spread ranges (ranked vs unranked):**
  | Rank | Expected Spread |
  |------|----------------|
  | #1-5 | 12-16 pts |
  | #6-10 | 9-12 pts |
  | #11-15 | 7-9 pts |
  | #16-20 | 5-7 pts |
  | #21-25 | 3-5 pts |
- **Star thresholds:** 16+ PPG and 30+ MPG, or 12 PPG with 5+ APG, or 12 PPG with 8+ RPG.
- **Sunday penalty:** -4 (36.1% dog cover — worst day).
- **ATS bounce-back:** +2 when lean team has <40% ATS (teams with bad ATS records revert to mean, +9.8% lift).
- **Spread sweet spot:** +3 for 6-10pt spreads (67.9%), -3 for <3 (34.7%), -2 for 15+ (47.4%).
- **Home/away split:** Removed (was +3, -7.9% lift).
- **H2H:** Removed (was +3/+2, -2.2% lift — noise).
- **Moneyline threshold:** 7+ points. No player props (excluded from PRISM).

### NFL
- **Timezone:** PST (UTC-8) for slot classification, EST for display
- **Slot rules:**
  - Thursday = public
  - Sunday early (10 AM PST) = public
  - Sunday late (1 PM PST) = vegas
  - Sunday Night Football = **SKIP** (do not bet)
  - Last non-SNF Sunday game = public override
  - Monday Night = vegas (trap)
- **Lean direction flipped:** Public = underdog (58% cover), Vegas = favorite (56.2% cover). This was the single biggest backtesting improvement (+28.9% ROI swing).
- **Line direction:** +3 toward dog, -2 toward fav (like NBA).
- **Spread sweet spot:** +3 for 3-7pt spreads (65.2%), -3 for <3 (47.6%), -3 for 10+ (38.9%).
- **Trend Discrepancy** (vegas slots only): Analyzes last 4 games for both teams. Teams at 0-1 wins = bounce-back value, 3-4 wins = regression risk. +20% lift after lean flip.
- **O/U Analysis** (vegas slots only): Flags totals above 50.5 and divergence of 6+ points between the total and teams' combined scoring averages. +6.9% lift.
- **Weather:** 3-tier fetch (scoreboard inline, ESPN summary, OpenWeather fallback). Flags wind 15+ mph, temp 32F or below, and precipitation. Dome stadiums are auto-detected and skipped.
- **Home/away split:** Removed (was +3, -19.6% lift).
- **H2H:** Removed (was +3/+2, -33% lift — terrible).
- **Moneyline threshold:** 3+ points (field goal margin).

---

## PRISM Player Prop Engine (NBA, NHL, CBB)

PRISM (Player Rating & Integrated Statistical Model) is a multi-stat projection engine that runs on-demand for NBA, NHL, and CBB games. It analyzes the top 3 scorers on each team across sport-specific stat types.

| Sport | Stats Projected | Min Thresholds |
|-------|----------------|----------------|
| NBA | PTS, REB, AST | 8.0 PPG, 4.0 RPG, 3.0 APG |
| NHL | PTS, GOALS, AST, SOG | 0.5 PPG, 0.2 GPG, 0.3 APG, 1.5 SOG/G |
| CBB | PTS, REB, AST | 8.0 PPG, 4.0 RPG, 3.0 APG |

### Projection Formula

```
projection = (weighted_avg * matchup * pace * rest * home_away * blowout) + usage_boost
```

| Component | Weight/Range | Description |
|-----------|-------------|-------------|
| Weighted average | 60% recent / 40% season | Last 5 games (15+ min, 10+ for NHL) blended with season avg |
| Matchup multiplier | 0.85-1.20 (PTS/GOALS), 0.88-1.15 (SOG), 0.92-1.10 (AST) | Opponent defense vs league average |
| Pace factor | 0.90-1.15 | Game total / league average total |
| Rest factor | 0.93 if B2B | Back-to-back fatigue discount |
| Home/away | 1.03 home, 0.98 away | Home court/ice advantage |
| Blowout discount | Continuous ramp from spread threshold | NHL: starts at 1.5 spread, NBA/CBB: starts at 6 spread |
| Usage boost | +lost_ppg * 0.6 / weighted rank | Redistributed scoring from injured teammates |

### Signal Classification

PRISM combines the edge (projection - line) with slot type:

| Condition | Signal |
|-----------|--------|
| Vegas slot + under (2+ pts) | STRONG UNDER |
| Public slot + over (2+ pts) | STRONG OVER |
| Vegas slot + over (2+ pts) | SKIP (don't fight the slot) |
| 1-2 pt edge | LEAN OVER / LEAN UNDER |
| < 1 pt edge | PASS |

### Additional PRISM Features
- **Streak detection:** Flags when 4+ of last 5 games went in the same direction vs the line
- **Minutes volatility:** Standard deviation of recent minutes; flags instability when stdev > 5
- **Confidence score:** 0-100 based on edge magnitude, data quality, matchup data, streaks, and minutes stability
- **Line source:** Uses The-Odds-API posted lines when available, falls back to estimated lines (season avg * discount factor)
- **Estimated line cap:** Signals capped at LEAN when line source is estimated (no STRONG on estimated lines)
- **Combo props:** PTS+REB+AST (NBA/CBB), GOALS+AST and PTS+SOG (NHL)

---

## Prop EV Engine

Variance-based expected value calculation for player props, using PRISM projections combined with real market odds from The-Odds-API.

- **Win probability:** Base confidence + edge boost + signal adjustment, capped 10-95%
- **EV%:** `(probability - 52.4) / 52.4 * 100` (vs -110 breakeven at 52.4%)
- **EV units:** `(prob * 90.91) - ((1-prob) * 100)` assuming $100 bet
- **Variance computation:** Uses actual game log data to compute player stat variance for more accurate probability estimates
- Filters to positive EV props only, sorted by EV%
- Supports NBA, NHL, and CBB player prop markets

---

## EV Models (Spread Bets)

L2-regularized logistic regression models that replace heuristic scoring for spread bet evaluation. Trained via walk-forward validation on historical data.

| Sport | Features | Training | AUC Gate |
|-------|----------|----------|----------|
| NBA | 12 (spread, CLV, rest, offense, ratings, win%, home/away) | 500/100/100 split, C=0.1 | >= 0.58 |
| NHL | 8 (spread, CLV, line movement, rest, goals, total) | 250/50/50 rolling, C=0.05 | >= 0.53 |
| CBB | 8 (spread, CLV, line movement, rest, PPG, efficiency, total) | 250/50/50 rolling, C=0.05 | >= 0.53 |

Models use Bayesian regression (shrinks recent stats toward season average) and isotonic calibration when ECE > 5%.

---

## Bet Tracker

Personal bet slip for admin users with dual Supabase/SQLite persistence:

- **Track spread bets** directly from scan result cards
- **Track prop bets** from PRISM player prop rows
- **Auto-grading:** Spread bets graded via ESPN final scores; prop bets graded via player game logs (NBA and NHL)
- **CLV tracking:** Closing line value computed for spread bets (Odds API + ESPN fallback) and prop bets (closing odds comparison)
- **Dashboard:** Overall record, win rate with Wilson CI, ROI, streak, breakdowns by sport/type/recommendation/stat
- **Auto-grade on scan:** Background scan cache triggers grading after each hourly refresh

---

## Features

### Get Picks (Auto Scanner)
Scans all games for the selected sport, analyzes each one, and ranks them by confidence. Games above 68.5% cover are shown as picks. When no games clear the threshold, the top 5 closest calls are shown as alternatives. Games between 58-68.5% appear as "Other Games to Watch" below the main picks.

### ALL Mode
Scans all five sports simultaneously using parallel threads. Displays results grouped by sport with cross-sport parlay suggestions.

### Parlay Suggestions
Auto-generated from the day's picks:
- **Two-Face's Safe Bet** -- 2 legs, both 80%+ cover
- **Gotham Gambit** -- 4-6 legs, all 67.5%+ cover
- **Gotham Breakout** -- 4-10 legs, all 60%+ cover

### Joker's Lotto
Cross-sport mega parlay. Takes the single best pick (72%+ cover) from each sport and combines them into one ticket. Requires at least 2 qualifying sports.

### Manual Prediction (NBA only)
Enter a player name, team, and Vegas line to get an individual over/under projection based on recent game averages, slot type, line movement, and injury context.

### The Ledger (Prediction Tracker)
Every qualifying pick (68.5%+ cover) is saved to a SQLite database (PostgreSQL in production). The Ledger dashboard shows:
- Overall record and win rate
- Breakdowns by sport, slot type, and recommendation tier
- All predictions with HIT/MISS/PUSH results
- Auto-grading: fetches final scores from ESPN and grades pending predictions on dashboard load

### Feedback Loop
The system learns from its own history. The Ledger's tracked results feed back into scoring:
- +2 if this slot type + sport has >60% hit rate (minimum 20 decided games)
- -2 if hit rate <45%
- +1/-1 overall sport adjustment (minimum 50 decided games)
- Cached with 5-minute TTL to avoid DB churn

### ATS Record Factor
Checks the Ledger for the lean team's historical against-the-spread record:
- +4 if >60% ATS (minimum 3 decided games)
- -3 if <40% ATS (removed for NHL; flipped to +2 bounce-back for CBB)

### Sharp Money Detection
When `THE_ODDS_API_KEY` is set, compares Pinnacle (sharpest book) spreads against consensus:
- +5 in vegas slot when Pinnacle diverges 1.5+ pts from consensus and aligns with lean
- +3 in public slot when sharp and public money are aligned with lean

### Head-to-Head / Revenge Games
Looks up the most recent matchup between the two teams:
- +1 to +3 if lean team lost the prior meeting by the sport's threshold (revenge motivation)
- +2 if lean team dominated the prior meeting (continued dominance)
- Thresholds: NBA 10 pts, NHL 3 goals, CFB/CBB 10 pts, NFL 7 pts
- Removed for CBB, NHL, and NFL (backtested as noise or harmful)

### Rules Backtest Engine
Replays the production scoring system against historical outcomes to validate and tune scoring weights:
- Imports the same `_determine_lean`, `_calculate_score`, `classify_slot` functions used in production
- Tracks factor-level accuracy (fire rate, lift) to identify helpful vs harmful signals
- Generates threshold sweeps, slot breakdowns, recommendation breakdowns
- Factors NOT replayable: Trell Rule (no historical injury data), Public betting (no Pinnacle history), Feedback loop (no ledger at game time), NFL weather (no historical weather)

### Today + Tomorrow Slate
The scanner automatically fetches both today's active games and tomorrow's full slate. Tomorrow's games get a lightweight analysis (skip expensive API calls like PRISM, B2B, H2H, NFL weather/trends) since deep analysis isn't needed yet.

### Background Scan Cache
Two-tier cache (in-memory + Supabase persistent) for instant page loads:
- On startup: queues all sports for immediate warm-up scan
- On visitor arrival (`/api/games`): queues an immediate background refresh for that sport
- `/api/scan` returns cached results instantly, then triggers a background re-scan
- Periodic full refresh every hour for all cached sports (2 at a time with stagger delay)
- Daily 6 AM EST pre-scan of all sports + auto-grading of tracked bets
- File lock prevents duplicate scan threads across gunicorn workers

---

## Authentication

Optional Supabase authentication gate:
- Supabase JS CDN in `index.html`, auth-gate div as first body child
- `require_auth` decorator on all `/api/*` routes (except `/api/auth/config`)
- `authFetch()` wrapper in app.js injects Bearer token, auto-signs out on 401
- PyJWT for server-side JWT verification (ES256 via JWKS, HS256 fallback)
- When `SUPABASE_JWT_SECRET` is empty, auth is bypassed (local dev mode)

---

## Architecture

```
app.py                Flask routes + API endpoints
game_scanner.py       Analysis engine — scans and scores all games, PRISM orchestration
api_client.py         ESPN API integration (scoreboard, summary, injuries, stats, game logs)
api_players.py        BallDontLie NBA player stats + ESPN game logs for NHL/CBB
api_odds.py           The-Odds-API spreads, player props (NBA/NHL/CBB), ESPN weather
api_cache.py          Shared HTTP caching (10-min TTL, bounded to 500 entries)
time_slots.py         Slot classification rules per sport
line_movement.py      Spread movement detection + confirmation logic
trell_rule.py         Star player injury analysis (per-sport thresholds)
rank_analysis.py      CFB/CBB rank tiers, spread discrepancy, rank scam detection
analysis_factors.py   All scoring factors, NFL helpers, lean determination
constants.py          Recommendation thresholds, max scores, ML thresholds
prism.py              PRISM player prop projection engine (pure math, no API calls)
prop_ev_engine.py     Variance-based EV calculation for player props
projections.py        Manual prediction math (over/under probability)
calibration.py        Logistic calibration for cover probability (replaces linear formula)
tracker.py            SQLite/Supabase prediction storage + grading + dashboard stats
bet_tracker.py        Personal bet slip — track, grade, CLV for spread + prop bets
pick_curation.py      Pick curation and sync from scan results
scan_cache.py         Background scan cache daemon (thread-safe, hourly refresh)
cache_manager.py      Supabase persistent cache for scan results across deploys
nba_ev_model.py       L2-regularized logistic EV model for NBA spreads
nhl_ev_model.py       L2-regularized logistic EV model for NHL spreads
cbb_ev_model.py       L2-regularized logistic EV model for CBB spreads
frontend/             React + Vite SPA (TypeScript, Tailwind, shadcn/ui)
templates/            Legacy Flask templates (index.html)
static/               Legacy frontend (app.js, style.css)
test_model/           Backtesting engine (collector, rules backtest, EV models, NBA rebuild)
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/games` | GET | Today + tomorrow games for ticker, autocomplete, and hero cards |
| `/api/scan` | POST | Scan all games for a sport (or `"all"` for all 5). Returns cached results instantly |
| `/api/props` | GET | Load PRISM player props for a specific game (NBA, NHL, CBB) |
| `/api/top-props` | GET | Top props across all games for a sport, sorted by confidence |
| `/api/ev/player-props` | GET | Positive EV player props with variance-based probability |
| `/api/prop-ev` | GET | Detailed prop EV analysis for a specific game |
| `/api/predict` | POST | Manual player prop prediction (NBA) |
| `/api/dashboard` | GET | Ledger stats, breakdowns, and all predictions (auto-grades pending) |
| `/api/grade` | POST | Manually trigger grading of pending predictions |
| `/api/bets/save` | POST | Save tracked bets (spread or prop) |
| `/api/bets` | GET | Fetch tracked bets with optional sport/status filters |
| `/api/bets/grade` | POST | Grade all pending tracked bets |
| `/api/bets/dashboard` | GET | Bet tracker dashboard with aggregated stats |
| `/api/bets/<id>` | DELETE | Delete a pending tracked bet |
| `/api/auth/config` | GET | Supabase configuration (public, no auth required) |
| `/api/auth/me` | GET | Current user info and admin status |

### Test Model Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tm/collect` | POST | Start background historical data collection |
| `/api/tm/collect/status` | GET | Poll collection progress |
| `/api/tm/rules-backtest` | POST/GET | Start/get rules replay backtest |
| `/api/tm/rules-backtest/status` | GET | Poll rules backtest progress |
| `/api/tm/metrics` | GET | Get backtest performance metrics |
| `/api/tm/nba-ev/train` | POST | Train NBA EV logistic model |
| `/api/tm/nhl-ev/train` | POST | Train NHL EV logistic model |
| `/api/tm/cbb-ev/train` | POST | Train CBB EV logistic model |

### Data Sources

| Source | Used For |
|--------|----------|
| **ESPN Scoreboard API** | Game schedules, scores, rankings, venue data, inline weather |
| **ESPN Summary API** | Spreads (opening + current), over/under, detailed weather |
| **ESPN Injuries API** | Team injury reports with player IDs and status |
| **ESPN Player Stats API** | Season averages for star player identification |
| **ESPN Game Log API** | Recent game-by-game stats for PRISM projections |
| **ESPN Team Stats API** | Roster leaders, defensive ratings for PRISM |
| **ESPN Previous Matchup API** | Head-to-head history for revenge/dominance detection |
| **balldontlie.io** | NBA player game logs for manual predictions |
| **The-Odds-API** | Multi-book spreads (Pinnacle vs consensus), player prop lines (NBA: PTS/REB/AST, NHL: goals/assists/points/SOG) |
| **OpenWeatherMap** | Fallback weather data for NFL outdoor games |

### Caching Strategy

| Layer | TTL | Max Size | Purpose |
|-------|-----|----------|---------|
| HTTP response cache | 10 minutes | 500 entries | Avoid hammering ESPN/Odds APIs during concurrent analysis |
| Scan results cache | 1 hour | Per-sport | Instant page loads, background refresh on demand |
| Persistent scan cache | 1 hour | Per-sport | Supabase-backed cache survives deploys |
| Feedback loop cache | 5 minutes | ~50 entries | Avoid repeated Ledger DB queries during scan |
| Player ID cache | Session | 500 entries | Avoid redundant balldontlie lookups (evicts oldest 20%) |
| Game log cache | 30 minutes | 200 entries | Avoid re-fetching player game logs between prop loads |
| Props cache | On-demand | 50 entries | Cache PRISM results per event |
| Thread-safe | All layers | -- | Locks prevent race conditions during parallel game analysis |

### Concurrency

The scanner uses configurable thread pools for maximum throughput:
- `SCAN_GAME_WORKERS` (default 10): parallel game analysis
- `SCAN_API_WORKERS` (default 8): parallel API calls within each game
- PRISM fires all roster leader, game log, B2B, and defensive stat lookups in parallel
- `scan_all_games("all")` scans all 5 sports in parallel with `ThreadPoolExecutor`

### Stale Game Handling
Games that started 2+ hours ago are filtered out. Games with `STATUS_FINAL` are excluded. When all of today's games are finished, the tool automatically shows tomorrow's slate alongside any remaining today games.

---

## Star Player Thresholds (Trell Rule)

| Sport | Primary | Alternates |
|-------|---------|------------|
| NBA | 18+ PPG and 28+ MPG | 15 PPG + 5 APG, or 15 PPG + 8 RPG |
| NHL | 0.8+ PTS/G and 18+ TOI | 0.4 G/G + 16 TOI, or 0.5 A/G + 16 TOI |
| NFL | 230+ Pass YPG and 55+ QBR | 75 Rush YPG + 6 TD, or 65 Rec YPG + 5 TD |
| CBB | 16+ PPG and 30+ MPG | 12 PPG + 5 APG, or 12 PPG + 8 RPG |

The Trell Rule only fires when: the player is a star, status is "Out", the injury is recent (within 72 hours), and the game is in a vegas slot.

---

## Backtested Performance

**Important:** In-sample numbers are optimistic — they were derived from the same data used to tune the model. Out-of-sample (walk-forward) results are the honest measure. All accuracy figures include 95% Wilson confidence intervals.

### Data Confidence Levels

| Sport | Games | Confidence | Notes |
|-------|-------|------------|-------|
| CBB | 1,977 | **High** | Sufficient for most factor validation |
| NBA | 607 | **Medium** | Adequate for core factors, marginal for sub-splits |
| NHL | 529 | **Medium** | Adequate for core factors |
| NFL | 105 | **Low** | Insufficient for reliable weight tuning |
| CFB | 51 | **Very Low** | All weights essentially unvalidated |

### In-Sample Results (Rules Replay)

| Sport | STRONG PLAY | LEAN | Overall |
|-------|-------------|------|---------|
| NBA | 74.1% [62.0%-83.6%] (n=58) | 53.9% [45.2%-62.4%] (n=128) | 60.6%, +15.6% ROI |
| NHL | 79.0% [56.7%-91.5%] (n=19) | 66.1% [59.1%-72.4%] (n=186) | 65.9% |
| CBB | -- | -- | 65.8%, +25.6% ROI |
| NFL | -- | -- | 56.8%, +19.3% ROI |

*These numbers were derived from the same data used to tune the model — they overstate real-world performance.*

### Out-of-Sample Results (Walk-Forward Validation)

Walk-forward validation derives weights from training data only and evaluates on held-out test games the model has never seen. Rolling mode uses 200-game training / 50-game test sliding windows; split mode uses a single 70/30 chronological split.

**Run date:** 2026-02-25

| Sport | Mode | Folds | Test Games | Overall Acc | 95% Wilson CI | ROI | Verdict |
|-------|------|-------|------------|-------------|---------------|-----|---------|
| NHL | Rolling | 6 | 300 | **67.33%** | [61.8%-72.4%] | **+28.5%** | **VALIDATED** |
| CBB | Rolling | 11 | 550 | 49.09% | [44.9%-53.3%] | -6.3% | Coin flip |
| NBA | Rolling | 8 | 400 | 49.0% | [44.1%-53.9%] | -6.5% | Coin flip |
| NFL | Split | 1 | 29 | 34.48% | [19.9%-52.7%] | -34.2% | UNRELIABLE |
| CFB | -- | -- | -- | -- | -- | -- | Too few games (51 < 65 minimum) |

#### Qualified Bets (Score >= Derived Lean Threshold)

| Sport | Qualified Bets | Qualified Acc | 95% Wilson CI | Qualified ROI |
|-------|---------------|---------------|---------------|---------------|
| NHL | 189 | **62.43%** | [55.4%-69.0%] | **+20.0%** |
| CBB | 250 | 51.2% | [45.0%-57.3%] | -2.0% |
| NBA | 170 | 50.59% | [43.1%-58.0%] | -8.6% |
| NFL | 19 | 26.32% | [11.8%-48.8%] | -49.8% |

#### Overfitting Gap (In-Sample vs Out-of-Sample)

| Sport | In-Sample Acc | OOS Acc | Gap | Status |
|-------|--------------|---------|-----|--------|
| NHL | 65.9% | 67.33% | **-1.4%** (OOS higher) | Weight calibration confirmed |
| CBB | 65.8% | 49.09% | **16.7%** | **SUSPECT — weights overfit to tuning data** |
| NBA | 60.6% | 49.0% | **11.6%** | **SUSPECT — weights overfit to tuning data** |
| NFL | 56.8% | 34.48% | **22.3%** | **SUSPECT** — but only 29 test games, noise dominates |

#### Key Findings

1. **NHL is the only validated model.** Out-of-sample accuracy (67.33%) matches in-sample (65.9%), confirming the "always underdog" lean and slot classification are real signals. Stable across all 6 folds (54-76% range, 5 of 6 folds above 62%).

2. **NBA and CBB production weights are overfit.** Both sports drop to coin-flip accuracy (~49%) out-of-sample. The walk-forward engine couldn't derive consistent weights — most factors shrink to 0 because they don't pass statistical significance with 200-game training windows. The in-sample numbers (60.6% NBA, 65.8% CBB) were artifacts of tuning to the same data.

3. **NFL results are noise.** With only 29 test games and weight tuning locked to production defaults, the 34.5% accuracy has a Wilson CI spanning [19.9%-52.7%]. The 22.3% gap is dramatic but statistically meaningless at this sample size.

4. **CFB cannot be validated.** Only 51 eligible games — below the 65-game minimum required to build even a single fold.

5. **Line movement remains the strongest signal**, but even it couldn't overcome the noise in NBA/CBB walk-forward folds. NHL's success appears driven primarily by the base "always lean underdog" strategy (+6 public slot bonus) rather than individual factor weights.

### Known Limitations

- **NBA and CBB weight calibrations are suspect**: Walk-forward validation shows both sports at coin-flip accuracy out-of-sample. The in-sample numbers (60.6% NBA, 65.8% CBB) were derived from the same data used to tune weights and do not generalize. These sports need larger datasets or fundamentally different approaches.
- **NFL and CFB weights are unvalidated**: With only 105 and 51 games respectively, sport-specific overrides (NFL lean flip, spread buckets) lack statistical significance. NFL overrides fall back to universal defaults via the overfitting protection framework.
- **Non-replayable factors inflate in-sample numbers**: Trell Rule (+5), public betting (+3/+5), feedback loop, and NFL weather cannot be replayed in backtests. Their actual contribution is unknown.
- **NHL is the only sport where production weights are confirmed by out-of-sample testing.** All other sports should be treated as experimental until more data is collected or weight derivation is improved.
- **Small training windows limit factor discovery**: The 200-game rolling windows may be too small to detect weak but real signals. Factor weights that require 300+ games to validate (per MIN_GAMES_WEIGHT_TUNING) cannot be properly derived in walk-forward folds.

---

## Overfitting Protection

Every sport-specific weight override (day penalties, spread buckets, lean direction, factor weights) was derived from the same historical data it's evaluated on, creating overfitting risk. A regularization framework constrains weight derivation and requires statistical evidence before applying overrides.

### Confidence Registry

All sport-specific overrides are tracked in `SPORT_OVERRIDES` (`constants.py`) with metadata:

| Field | Description |
|-------|-------------|
| `value` | The override value |
| `n` | Sample size used to derive it |
| `p_value` | Statistical significance (proportion z-test) |
| `confidence` | Tier: `validated`, `weak`, or `insufficient_data` |

Only **validated** overrides are applied in production scoring. Weak and insufficient_data overrides fall back to `UNIVERSAL_DEFAULTS` (pre-tuning baselines).

**Impact:** NFL's lean flip (n=105, insufficient_data) falls back to slot_dependent defaults. Many NBA spread bucket adjustments are "weak" and fall back to 0.

### Evidence Thresholds

Each override category has minimum sample size and p-value requirements:

| Category | Min Games | p-value Threshold |
|----------|-----------|-------------------|
| Day penalty | 40 | 0.05 |
| Spread bucket | 50 | 0.05 |
| Factor weight | 100 | 0.10 |
| Lean direction | 200 | 0.05 |

### L2 Regularization

Walk-forward weight derivation applies an L2 penalty that penalizes deviation from universal defaults:

```
penalty = lambda * sum((derived_weight - default_weight)^2)
```

This soft constraint shrinks extreme derived values back toward baselines, reducing overfitting to training folds. Applied in:
- Threshold sweep (penalized accuracy for cutoff selection)
- Factor weight derivation (weights shrunk toward defaults after computation)

### Statistical Testing

The walk-forward engine (`walkforward.py`) applies proportion z-tests at every derivation step:
- **Lean direction:** Requires n >= 200 and p < 0.05 in both public and vegas slots to flip from default
- **Day penalties:** Requires n >= 40 and p < 0.05 vs overall dog cover rate
- **Spread buckets:** Requires n >= 50 and p < 0.05 vs overall dog cover rate
- **Factor weights:** Factors with 100+ fires require p < 0.10 for full weight; 30-100 fires cap at +/-2; below 30 zeroed out

---

## Usage

```bash
python app.py
```

Open `http://localhost:5000`. Click a sport card on the hero page to auto-scan, or open the sidebar for manual player props.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | No | Supabase project URL for authentication |
| `SUPABASE_ANON_KEY` | No | Supabase anonymous key for client-side auth |
| `SUPABASE_JWT_SECRET` | No | JWT secret for server-side verification (empty = bypass auth) |
| `OPENWEATHER_API_KEY` | No | Enables fallback weather data for NFL outdoor games |
| `THE_ODDS_API_KEY` | No | Enables sharp money detection and posted player prop lines |
| `ODDS_API_KEY` | No | Odds API key for historical spread backfill in backtesting |
| `DATABASE_URL` | No | PostgreSQL connection string for production (defaults to local SQLite) |
| `PORT` | No | Server port (default 5000) |
| `SCAN_GAME_WORKERS` | No | Thread pool size for parallel game analysis (default 10) |
| `SCAN_API_WORKERS` | No | Thread pool size for parallel API calls per game (default 8) |

### Dependencies

```
flask
requests
gunicorn
psycopg2-binary
scikit-learn
numpy
PyJWT
cryptography
supabase
```
