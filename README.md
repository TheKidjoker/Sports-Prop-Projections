# Joker's Edge

A rules-based sports betting analysis engine that evaluates spread plays across **NBA**, **NHL**, **CFB**, **CBB**, and **NFL**. Combines time-slot theory, line movement tracking, injury impact analysis, and sport-specific intelligence signals to produce a confidence score for every game on the board.

## Core Theory

Not all time slots are created equal. Vegas adjusts its edge depending on when games are played, who's watching, and where the money flows. This tool classifies every game into a **slot type** (public or vegas), then layers confirmation factors on top to build a composite score and cover percentage.

- **Public slots** produce sensible, chalk outcomes — lean with the favorite.
- **Vegas slots** are where the books hold the edge and sharp money dominates — lean with the underdog.

## How Scoring Works

Each game starts at a base of 50% cover probability. Confirmation factors add points to a composite score, which maps linearly to a cover percentage:

```
cover_pct = 50 + (score / max_score) * 45
```

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
| Large spread penalty | -3 | All sports (thresholds vary) |

**Max scores:** NBA/NHL = 23, CFB/CBB = 33, NFL = 38

Games scoring 68.5%+ cover are surfaced as picks. Below that, the top 5 closest games are shown as alternatives.

### Recommendation Labels

| Label | Score | Meaning |
|-------|-------|---------|
| **STRONG PLAY** | 15+ | Multiple confirmation factors align |
| **LEAN** | 10-14 | Some factors confirm, worth a look |
| **MONITOR** | 0-9 | Limited confirmation, watch but don't commit |

## Sports Supported

### NBA
- **Timezone:** PST (UTC-8) for slot classification, EST for display
- **Slot rules:** Day-of-week determines the slot schedule. Mon/Wed/Fri = public days, Tue/Thu/Sat/Sun = vegas days. Alternating public/vegas slots at specific tip-off times.
- **First-game override:** The first game of the day gets the opposite slot of the day type (public day first game = vegas, vegas day first game = public).
- **Player props:** Uses balldontlie.io API for individual player stats and over/under projections.
- **Moneyline threshold:** 6+ point spreads recommend ML instead of spread.

### NHL
- **Timezone:** CST (UTC-6) for slot classification, EST for display
- **Slot rules:** Based on slate size, not day of week:
  - 1 game = vegas
  - 2 games = first is public, second is vegas
  - 3+ games = time-based classification using CST start times
- **Moneyline:** Not used (puck line sport, ML doesn't apply the same way).

### CFB (College Football)
- **Timezone:** EST (UTC-5) for both classification and display
- **Slot rules:** Day overrides (Thu/Fri = public, Mon = trap, Sun = public) + Saturday time-based slots
- **Rank Scam:** Detects when a higher-ranked team is at home but listed as the underdog. In public slots, the ranked home underdog is expected to cover. In vegas slots, fade them.
- **Spread Discrepancy:** Flags games where the actual spread is significantly below the expected range for a ranked team's tier vs an unranked opponent.
- **Rank tiers:**
  - Frontend (#1-9): Public darlings, don't expect big spread covers
  - Middle (#10-19): Case by case
  - Backend (#20-25): Under the radar, expected to cover
- **Moneyline threshold:** 7+ points (touchdown margin).

### CBB (College Basketball)
- **Timezone:** EST (UTC-5) for both classification and display
- **Slot rules:** Day overrides (Mon/Tue = vegas/sharp, Wed-Fri = public, Sun = public) + Saturday time-based slots
- **Rank Scam + Spread Discrepancy:** Same logic as CFB with basketball-calibrated expected spreads (~half of CFB ranges).
- **Star thresholds:** 16+ PPG and 30+ MPG, or 12 PPG with 5+ APG, or 12 PPG with 8+ RPG.
- **Moneyline threshold:** 7+ points. Spread penalty triggers at 14+.
- **No player props** (excluded from manual prediction).

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

## Lean Logic

The tool determines which team to lean towards based on slot type and spread:

- **Public/caution slot** = lean favorite (public money tends to be right in these spots)
- **Vegas/trap slot** = lean underdog (sharp money fades the public)

Spread convention: negative = home team favored. The action string includes the spread value and a "don't take past" limit (spread minus 1.5 points).

When the spread exceeds the sport-specific moneyline threshold, the tool recommends taking the moneyline instead of the spread.

## Features

### Get Picks (Auto Scanner)
Scans all games for the selected sport, analyzes each one, and ranks them by confidence. Games above 68.5% cover are shown as picks. When no games clear the threshold, the top 5 closest calls are shown as alternatives. Games between 58-68.5% appear as "Other Games to Watch" below the main picks.

### ALL Mode
Scans all five sports simultaneously using parallel threads. Displays results grouped by sport with cross-sport parlay suggestions.

### Parlay Suggestions
Auto-generated from the day's picks:
- **Two-Face's Safe Bet** — 2 legs, both 80%+ cover
- **Gotham Gambit** — 4-6 legs, all 67.5%+ cover
- **Gotham Breakout** — 4-10 legs, all 60%+ cover

### Joker's Lotto
Cross-sport mega parlay. Takes the single best pick (72%+ cover) from each sport and combines them into one ticket. Requires at least 2 qualifying sports.

### Manual Prediction (NBA only)
Enter a player name, team, and Vegas line to get an individual over/under projection based on recent game averages, slot type, line movement, and injury context.

### The Ledger (Prediction Tracker)
Every qualifying pick (68.5%+ cover) is saved to a SQLite database. The Ledger dashboard shows:
- Overall record and win rate
- Breakdowns by sport, slot type, and recommendation tier
- Last 50 predictions with HIT/MISS/PUSH results
- Manual grading button that fetches final scores from ESPN

## Architecture

```
app.py              Flask routes + API endpoints
game_scanner.py     Analysis engine — scans and scores all games
api_client.py       ESPN API + balldontlie.io + OpenWeather integration
time_slots.py       Slot classification rules per sport
line_movement.py    Spread movement detection + confirmation logic
trell_rule.py       Star player injury analysis
projections.py      Player prop math (over/under probability)
tracker.py          SQLite prediction storage + grading + dashboard stats
templates/          index.html (single-page app)
static/             app.js (frontend logic), style.css (dark theme)
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/games` | GET | Today's games for ticker + autocomplete |
| `/api/scan` | POST | Scan all games for a sport (or all sports) |
| `/api/predict` | POST | Manual player prop prediction |
| `/api/dashboard` | GET | Ledger stats and recent predictions |
| `/api/grade` | POST | Grade pending predictions with final scores |

### Data Sources
- **ESPN Scoreboard API** — game schedules, scores, rankings, venue data, inline weather
- **ESPN Summary API** — spreads (opening + current), over/under, detailed weather
- **ESPN Injuries API** — team injury reports with player IDs and status
- **ESPN Player Stats API** — season averages for star player identification
- **balldontlie.io** — NBA player game logs for manual predictions
- **OpenWeatherMap** — fallback weather data for NFL outdoor games

### Caching
All ESPN API calls go through a thread-safe TTL cache (120 seconds) to avoid hammering the API during concurrent analysis. Games auto-refresh every 3 minutes via frontend polling.

### Stale Game Handling
Games that started 2+ hours ago are filtered out. When all of today's games are finished, the tool automatically fetches tomorrow's slate.

## Usage

```
python app.py
```

Open `http://localhost:5000`. Pick a sport, click **Get Picks**, or use the sidebar form for manual player props.

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENWEATHER_API_KEY` | No | Enables fallback weather data for NFL games |
