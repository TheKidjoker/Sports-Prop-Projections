# Joker's Edge

A rules-based sports betting analysis engine that evaluates spread plays across **NBA**, **NHL**, **CFB**, **CBB**, and **NFL**. Combines time-slot theory, line movement tracking, injury impact analysis, player prop projections, sharp money detection, and sport-specific intelligence signals to produce a confidence score for every game on the board.

Built with a dark red/black Gotham-themed UI ("Joker's Edge"), featuring a welcome hero landing page with sport cards, auto-scan on click, and an instant-load background cache system.

---

## Core Theory

Not all time slots are created equal. Vegas adjusts its edge depending on when games are played, who's watching, and where the money flows. This tool classifies every game into a **slot type** (public or vegas), then layers confirmation factors on top to build a composite score and cover percentage.

- **Public slots** produce sensible, chalk outcomes — lean with the favorite.
- **Vegas slots** are where the books hold the edge and sharp money dominates — lean with the underdog.

---

## How Scoring Works

Each game starts at a base of 50% cover probability. Confirmation factors add points to a composite score, which maps linearly to a cover percentage:

```
cover_pct = 50 + (score / max_score) * 45
```

### Scoring Factors

| Factor | Points | Applies To |
|--------|--------|------------|
| Public slot classification | +10 | All sports |
| Line movement confirms slot | +0 to +8 | All sports (graduated by magnitude) |
| Trell Rule (star injury in vegas slot) | +5 | All sports |
| Rank Scam detected | +5 | CFB, CBB |
| Spread Discrepancy detected | +5 | CFB, CBB |
| Trend Discrepancy | +5 | NFL |
| O/U Discrepancy | +5 | NFL |
| Weather factor | +5 | NFL |
| Back-to-back rest advantage | +4 | NBA, NHL |
| Back-to-back fatigue penalty | -3 | NBA, NHL |
| ATS record bonus | +4 | All sports |
| ATS record penalty | -3 | All sports |
| Home/away split alignment | +3 | All sports |
| Sharp money divergence (vegas slot) | +5 | All sports |
| Sharp + public alignment (public slot) | +3 | All sports |
| Head-to-head revenge bonus | +3 | All sports |
| Head-to-head dominance bonus | +2 | All sports |
| Vegas Trap (cold favorite) | +5 to +7 | NBA |
| Feedback loop (ledger performance) | -2 to +3 | All sports |
| Large spread penalty | -3 | All sports (thresholds vary) |

### Max Scores by Sport

| Sport | Max Score |
|-------|-----------|
| NBA | 49 |
| NHL | 42 |
| CFB | 48 |
| CBB | 48 |
| NFL | 53 |

Games scoring 68.5%+ cover are surfaced as picks. Below that, the top 5 closest games are shown as alternatives. Games between 58-68.5% appear as "Other Games to Watch."

### Recommendation Labels

| Label | Score | Meaning |
|-------|-------|---------|
| **STRONG PLAY** | 15+ | Multiple confirmation factors align |
| **LEAN** | 10-14 | Some factors confirm, worth a look |
| **MONITOR** | 0-9 | Limited confirmation, watch but don't commit |

### Line Movement Scoring (Graduated)

| Movement | Points |
|----------|--------|
| 0-1 pts | 0 (noise) |
| 1-2 pts | 3 (mild signal) |
| 2-3 pts | 5 (solid signal) |
| 3+ pts | 8 (strong signal) |

### Spread Size Penalties

| Sport | Threshold | Penalty |
|-------|-----------|---------|
| NBA/NHL | > 8 pts | -3 |
| CFB/CBB | > 14 pts | -3 |
| NFL | > 10 pts | -3 |

---

## Sports Supported

### NBA
- **Timezone:** PST (UTC-8) for slot classification, EST for display
- **Slot rules:** Day-of-week determines the slot schedule. Mon/Wed/Fri = public days, Tue/Thu/Sat/Sun = vegas days. Alternating public/vegas slots at specific tip-off times.
- **First-game override:** The first game of the day gets the opposite slot of the day type (public day first game = vegas, vegas day first game = public).
- **Player props (PRISM):** Multi-stat projection engine for PTS, REB, AST on top 3 scorers per team (see PRISM section below).
- **Vegas Trap:** Detects heavy favorites (7+ pt spread) on cold streaks in vegas slots. +5 if favorite is cold (0-2 wins in last 7), +7 if both teams are cold.
- **Back-to-back detection:** +4 bonus when opponent is on a B2B, -3 penalty when lean team is on a B2B.
- **Moneyline threshold:** 6+ point spreads recommend ML instead of spread.

### NHL
- **Timezone:** CST (UTC-6) for slot classification, EST for display
- **Slot rules:** Based on slate size, not day of week:
  - 1 game = vegas
  - 2 games = first is public, second is vegas
  - 3+ games = time-based classification using CST start times
- **Back-to-back detection:** Same as NBA (+4/-3).
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
- **Slot rules:** Day overrides (Mon/Tue = vegas/sharp, Wed-Fri = public, Sun = public) + Saturday time-based slots
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
- **Moneyline threshold:** 7+ points. Spread penalty triggers at 14+.
- **No player props** (excluded from PRISM).

### NFL
- **Timezone:** PST (UTC-8) for slot classification, EST for display
- **Slot rules:**
  - Thursday = public
  - Sunday early (10 AM PST) = public
  - Sunday late (1 PM PST) = vegas
  - Sunday Night Football = **SKIP** (do not bet)
  - Last non-SNF Sunday game = public override
  - Monday Night = vegas (trap)
- **Trend Discrepancy** (vegas slots only): Analyzes last 4 games for both teams. Teams at 0-1 wins = bounce-back value, 3-4 wins = regression risk. Both signals in the same game = strong contrarian.
- **O/U Analysis** (vegas slots only): Flags totals above 50.5 and divergence of 6+ points between the total and teams' combined scoring averages.
- **Weather:** 3-tier fetch (scoreboard inline, ESPN summary, OpenWeather fallback). Flags wind 15+ mph, temp 32F or below, and precipitation. Dome stadiums are auto-detected and skipped.
- **Moneyline threshold:** 3+ points (field goal margin).

---

## Lean Logic

The tool determines which team to lean towards based on slot type and spread:

- **Public/caution slot** = lean favorite (public money tends to be right in these spots)
- **Vegas/trap slot** = lean underdog (sharp money fades the public)

Spread convention: negative = home team favored. The action string includes the spread value and a "don't take past" limit (spread minus 1.5 points).

When the spread exceeds the sport-specific moneyline threshold, the tool recommends taking the moneyline instead of the spread.

### Trell Rule Lean Override
When the Trell Rule fires (star player recently injured + out + vegas slot), the lean overrides to the star's team — the market overreacts to star injuries and creates value.

### Home/Away Split Bonus
+3 when the lean aligns with the natural home/away edge:
- Public slot + lean is home favorite
- Vegas slot + lean is road underdog

---

## PRISM Player Prop Engine (NBA)

PRISM (Player Rating & Integrated Statistical Model) is a multi-stat projection engine that runs on every NBA game. It analyzes the top 3 scorers on each team across three stat types: **PTS**, **REB**, and **AST**.

### Projection Formula

```
projection = (weighted_avg * matchup * pace * rest * home_away * blowout) + usage_boost
```

| Component | Weight/Range | Description |
|-----------|-------------|-------------|
| Weighted average | 60% recent / 40% season | Last 5 games (15+ min) blended with season avg |
| Matchup multiplier | 0.85-1.20 (PTS), 0.92-1.10 (AST) | Opponent defense vs league average |
| Pace factor | 0.90-1.15 | Game total / league average total (224) |
| Rest factor | 0.93 if B2B | Back-to-back fatigue discount |
| Home/away | 1.03 home, 0.98 away | Home court advantage |
| Blowout discount | 0.88 if spread > 10 | Reduced minutes in blowouts (PTS only) |
| Usage boost | +lost_ppg * 0.6 / 3 | Redistributed scoring from injured teammates |

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
- -3 if <40% ATS

### Sharp Money Detection
When `THE_ODDS_API_KEY` is set, compares Pinnacle (sharpest book) spreads against consensus:
- +5 in vegas slot when Pinnacle diverges 1.5+ pts from consensus and aligns with lean
- +3 in public slot when sharp and public money are aligned with lean

### Head-to-Head / Revenge Games
Looks up the most recent matchup between the two teams:
- +3 if lean team lost the prior meeting by the sport's threshold (revenge motivation)
- +2 if lean team dominated the prior meeting (continued dominance)
- Thresholds: NBA 10 pts, NHL 3 goals, CFB/CBB 10 pts, NFL 7 pts

### Today + Tomorrow Slate
The scanner automatically fetches both today's active games and tomorrow's full slate. Tomorrow's games get a lightweight analysis (skip expensive API calls like PRISM, B2B, H2H, NFL weather/trends) since deep analysis isn't needed yet.

### Background Scan Cache
Results are pre-computed and cached for instant page loads:
- On visitor arrival (`/api/games`): queues an immediate background refresh for that sport
- `/api/scan` returns cached results instantly, then triggers a background re-scan
- Periodic full refresh every hour for all cached sports
- No startup warm-up (avoids slow deploy loads)

---

## Architecture

```
app.py                Flask routes + API endpoints
game_scanner.py       Analysis engine — scans and scores all games
api_client.py         ESPN API integration (scoreboard, summary, injuries, stats)
api_players.py        BallDontLie NBA player stats (game logs, player ID lookup)
api_odds.py           The-Odds-API spreads, player props, ESPN weather
api_cache.py          Shared HTTP caching (10-min TTL) + ESPN URL builder
time_slots.py         Slot classification rules per sport
line_movement.py      Spread movement detection + confirmation logic
trell_rule.py         Star player injury analysis (per-sport thresholds)
rank_analysis.py      CFB/CBB rank tiers, spread discrepancy, rank scam detection
analysis_factors.py   All scoring factors, NFL helpers, lean determination
prism.py              PRISM player prop projection engine (pure math, no API calls)
projections.py        Manual prediction math (over/under probability)
tracker.py            SQLite/PostgreSQL prediction storage + grading + dashboard stats
scan_cache.py         Background scan cache daemon (thread-safe, hourly refresh)
templates/            index.html (single-page app)
static/               app.js (frontend logic), style.css (dark Gotham theme)
test_model/           Experimental ML overlay (collector, features, backtest, scanner)
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/games` | GET | Today + tomorrow games for ticker, autocomplete, and hero cards |
| `/api/scan` | POST | Scan all games for a sport (or `"all"` for all 5). Returns cached results instantly |
| `/api/predict` | POST | Manual player prop prediction (NBA) |
| `/api/dashboard` | GET | Ledger stats, breakdowns, and all predictions (auto-grades pending) |
| `/api/grade` | POST | Manually trigger grading of pending predictions |

### Test Model Endpoints (Experimental)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tm/collect` | POST | Start background historical data collection |
| `/api/tm/collect/status` | GET | Poll collection progress |
| `/api/tm/features` | POST | Compute features for collected data |
| `/api/tm/backtest` | POST | Start walk-forward backtest |
| `/api/tm/backtest/status` | GET | Poll backtest progress |
| `/api/tm/scan` | POST | Scan today's games with ML model overlay |
| `/api/tm/metrics` | GET | Get backtest performance metrics |

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
| **The-Odds-API** | Multi-book spreads (Pinnacle vs consensus), player prop lines (PTS/REB/AST) |
| **OpenWeatherMap** | Fallback weather data for NFL outdoor games |

### Caching Strategy

| Layer | TTL | Purpose |
|-------|-----|---------|
| HTTP response cache | 10 minutes | Avoid hammering ESPN/Odds APIs during concurrent analysis |
| Scan results cache | 1 hour | Instant page loads, background refresh on demand |
| Feedback loop cache | 5 minutes | Avoid repeated Ledger DB queries during scan |
| Thread-safe | All layers | Locks prevent race conditions during parallel game analysis |

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

## Usage

```bash
python app.py
```

Open `http://localhost:5000`. Click a sport card on the hero page to auto-scan, or open the sidebar for manual player props.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENWEATHER_API_KEY` | No | Enables fallback weather data for NFL outdoor games |
| `THE_ODDS_API_KEY` | No | Enables sharp money detection (Pinnacle vs consensus) and posted player prop lines for PRISM |
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
vaderSentiment
numpy
```
