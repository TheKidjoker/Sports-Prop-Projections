# Joker's Edge - Development Notes

## NBA Backtesting Results (V4 - Final)
- **Dataset**: 550+ NBA games collected via ESPN API
- **Actionable bets**: 51 | **Accuracy**: 62.7% | **ROI**: +19.8%
- **Previous (V1)**: 42.3% accuracy, -19.3% ROI

### Key Findings
1. **Public slot lean was backwards** — leaning the favorite in public slots hit only 37.5%. Flipping to always lean underdog jumped to 63.6%. NBA public money inflates favorite lines in ALL time slots, so fading the public = taking the dog.
2. **Spread penalty was counterproductive** — large spreads actually cover well in NBA. Removed the -3 penalty.
3. **Line movement has minimal lift in NBA** — reduced scores from 3/5/8 to 2/3/5.
4. **B2B and H2H were overweighted** — B2B reduced to +2/-1, H2H revenge to +1.
5. **Vegas slot dominates** — 63.2% accuracy vs public's ~50%. STRONG PLAY restricted to vegas-only (score >= 10), public capped at LEAN.
6. **Sweet spot at score >= 6**: 68.9% accuracy, +31.5% ROI (but fewer bets).

### NBA Weight Changes (vs other sports)
| Factor | NBA | Other Sports |
|--------|-----|--------------|
| Lean direction | Always underdog | Public=favorite, Vegas=underdog |
| Public slot bonus | +5 | +10 |
| Line movement | 2/3/5 | 3/5/8 |
| Spread penalty | None | -3 (>14 pts) |
| B2B bonus/penalty | +2/-1 | +4/-3 |
| H2H revenge | +1 | +3 |
| Max score | 39 | 49 (NHL), 33 (CBB), 35 (NFL) |
| STRONG PLAY | Vegas >= 10 only | >= 15 flat |
| LEAN | Vegas >= 5, Public >= 7 | >= 10 flat |

---

## NHL Backtesting Results
- **Status**: Not yet tested — need to collect data first
- **Dataset**: TBD
- **Current weights**: Default (public slot +10, line movement 3/5/8, B2B +4/-3, H2H +3, spread penalty -3, max score 49)

### Slot Logic (unique to NHL)
- 1 game slate = vegas
- 2 game slate = 1st game public, 2nd game vegas
- 3+ games = time-based (CST classification)

### Factors to Watch
- [ ] Does lean direction need flipping like NBA?
- [ ] Is spread penalty valid? (NHL spreads are small, typically 1.5)
- [ ] B2B impact — NHL back-to-backs are brutal, may need higher weight
- [ ] Slate size rules — validate if 1-game/2-game logic holds
- [ ] Home ice advantage — stronger in NHL than NBA home court?

### Weight Changes (after tuning)
_None yet — run backtest first_

---

## NFL Backtesting Results
- **Status**: Not yet tested — need to collect data first
- **Dataset**: TBD (season runs Sep-Feb, ~270 games/season)
- **Current weights**: Default (public slot +10, line movement 3/5/8, B2B N/A, H2H +3, max score 35)

### Slot Logic (unique to NFL)
- Thursday = public
- Sunday early = public
- Sunday late = vegas
- Sunday Night Football = skip
- Monday Night Football = vegas

### Unique Factors
- Trend discrepancy (vegas only): last-4 W/L bounce-back or regression
- O/U analysis (vegas only): high total + team avg divergence
- Weather factor (+5): wind/rain/snow at outdoor venues

### Factors to Watch
- [ ] Does lean direction need flipping like NBA?
- [ ] Thursday games — are they truly public or more random?
- [ ] SNF skip rule — should we actually skip or just treat differently?
- [ ] Weather impact — does +5 match real lift?
- [ ] Trend discrepancy — does last-4 W/L actually predict?
- [ ] O/U discrepancy — validate total-based flags

### Weight Changes (after tuning)
_None yet — run backtest first_

---

## CFB Backtesting Results
- **Status**: Not yet tested — need to collect data first
- **Dataset**: TBD (season runs Aug-Jan, 800+ games/season)
- **Current weights**: Default (public slot +10, line movement 3/5/8, spread penalty -3 >14pts, max score 49)

### Slot Logic (unique to CFB)
- Day-based overrides + Saturday time slots (EST classification)

### Unique Factors
- Rank scam (+5): ranked team vs unranked, spread doesn't match rank tier expectations
- Spread discrepancy (+5): spread out of range for team's rank tier
- Rank tiers: Frontend (#1-9) don't cover, Backend (#20-25) cover, Middle (#10-19) caution

### Factors to Watch
- [ ] Does lean direction need flipping like NBA?
- [ ] Rank scam — does it actually predict covers?
- [ ] Spread discrepancy — validate tier ranges are calibrated correctly
- [ ] Frontend ranks (#1-9) — confirm they don't cover ATS
- [ ] Backend ranks (#20-25) — confirm they do cover ATS
- [ ] Large spread penalty — CFB has bigger blowouts, is -3 right?
- [ ] Home field advantage — stronger in CFB than pros?

### Weight Changes (after tuning)
_None yet — run backtest first_

---

## CBB Backtesting Results (V1 - Tuned)
- **Dataset**: 789 CBB games collected via ESPN API (772 scored after warmup)
- **Actionable bets (LEAN+)**: 34 | **Accuracy**: 61.8% | **ROI**: +29.1%
- **At >=10 threshold**: 81 bets | 58.0% accuracy | +21.3% ROI
- **Baseline (pre-tune)**: ~50% accuracy, ~0% ROI

### Key Findings
1. **Line movement is the strongest signal** — +20.1% lift, 63.1% accuracy when it fires
2. **Public slot bonus was overweighted** — had -2.2% lift at +10, reduced to +5
3. **Spread penalty was counterproductive** — removed (actually had +8.8% lift when penalized, but inconsistent)
4. **Home/away split had negative lift** (-3.0%) — reduced from +3 to +1
5. **H2H revenge was noisy** — reduced from +3 to +1
6. **ATS record was noisy** — reduced from +4/−3 to +2/−1
7. **Saturday slot tolerance was too tight** — widened from 20 to 60 min, recovered 84 unknown-slot games
8. **Backend rank tier (#20-25)** covers only 46% in CBB (opposite of CFB) — message changed to "don't expect cover"

### CBB Weight Changes (V1)
| Factor | Before | After | Reason |
|--------|--------|-------|--------|
| Public slot bonus | +10 | +5 | -2.2% lift at +10 |
| Spread penalty | -3 (>14pts) | Removed | Inconsistent signal |
| ATS bonus/penalty | +4/−3 | +2/−1 | Noisy signal |
| Home/away split | +3 | +1 | -3.0% lift |
| H2H revenge | +3 | +1 | Too noisy |
| Sat slot tolerance | 20 min | 60 min | Recovered 84 games |
| STRONG PLAY | >= 15 | >= 15 | No change |
| LEAN | >= 10 | >= 12 | 10-14 is dead zone (45.9%) |
| Max score | 48 | 33 | Tighter bounds |

### CBB V2 Improvements — TODO (Push Toward 70-75%)

#### Immediate Code Changes (No New Data Needed)
- [ ] **Flip vegas slot lean to FAVORITE** — Vegas underdog lean is 0/2 at score>=12, 39.1% overall. This is the single biggest fix. Public slot (favorite lean) is where all the edge lives.
- [ ] **Remove h2h_revenge for CBB entirely** — 25% accuracy when firing. Actively harmful.
- [ ] **Boost ats_record weight** from +2 to +4 or +5 — strongest individual signal at 70.0% when firing at score>=12. slot_bonus + ats_record = 73.7% on 19 games.
- [ ] **Add spread floor filter** — |spread| < 3 is a coin flip (53%) even at high scores. Skip or downweight.
- [ ] **Cap line movement magnitude** — 1-2pt moves = 83.3%, 2-3pt = 75.0%, but 3+pt = 57.1%. Large moves dilute accuracy. Cap score at 2-3pt level.
- [ ] **Add ranked lean bonus** — when lean team is ranked #1-9, accuracy jumps to 81.2% on 16 games. Give +2 or +3 for top-tier ranked lean.

#### High-Value Filter Combos Found in Data
| Filter | Games | Accuracy | ROI |
|--------|-------|----------|-----|
| score>=12 + ats + home_away both fire | 10 | **80.0%** | +52.7% |
| score>=12 + slot_bonus + ats fire | 19 | **73.7%** | +40.7% |
| score>=12 + line_mvmt + spread_disc + lean_away | 8 | **75.0%** | +43.2% |
| score>=12 + spread 7-14 pts | 10 | **80.0%** | +52.7% |
| score>=12 + lean team ranked #1-9 | 16 | **81.2%** | +55.1% |
| line_mvmt + spread_disc + lean_away (score>=8) | 8 | **87.5%** | — |

#### Spread Range Analysis (at score>=12)
- |spread| 0-3: 53.3% (coin flip — avoid)
- |spread| 3-7: 69.2% (solid)
- |spread| 7-14: 80.0% (sweet spot)
- |spread| 14+: small sample, unreliable

#### Day-of-Week Highlights (at score>=12)
- Sunday: 75.0% (4 games — small but strong)
- Wednesday: 69.2% (13 games)
- Thursday: 63.6% (11 games)
- Saturday: 61.1% (18 games)
- Monday/Tuesday (vegas override): weak — consider skipping or flipping lean

#### Realistic Accuracy Targets
- **~67-70% on 30-45 games**: Public slot + score>=12 + at least one strong signal
- **~75% on 15-20 games**: Tight filter requiring multiple signals (ats + slot + score>=12)
- **~80% on 8-10 games**: Ultra-selective (ranked lean + mid-spread + ats firing)
- **75% at high volume**: Requires missing data signals (see below)

---

## TODO: Historical Injury Data for Backtest
- **Problem**: Trell Rule (+5 for star player out) can't be replayed in backtest because we don't have historical injury reports
- **Goal**: Integrate a historical injuries API to store who was OUT on each game date
- **API Options to Research**:
  - Sportradar — comprehensive historical injury data
  - SportsData.io — historical injury endpoints
  - MySportsFeeds — historical injury reports
- **Storage**: New `tm_historical_injuries` table: event_id, team, player, status, injury_date
- **Impact**: Would allow replaying Trell Rule, star player impact, and injury-adjusted scoring in backtest

## TODO: Historical Public Betting Data
- **Problem**: Public betting factor (+3/+5) can't be replayed without historical betting percentages
- **Goal**: Historical Pinnacle odds or public betting % data
- **Impact**: Would validate whether public betting % adds predictive value

## TODO: Historical NFL Weather
- **Problem**: NFL weather factor (+5) can't be replayed without weather at game time
- **Goal**: Historical weather data matched to game dates/venues
- **Options**: OpenWeather historical API, Visual Crossing, Weather API

---

## TODO: Tune Other Sports
Each sport needs its own data collection + rules replay cycle:
- [ ] **NHL** — Collect games, run rules replay, analyze factor lifts, tune weights
- [ ] **NFL** — Same process (season data available Sep-Feb)
- [ ] **CFB** — Same process (rank scam/spread discrepancy are unique factors to validate)
- [x] **CBB** — V1 tuned (61.8% / +29.1% ROI). V2 improvements identified (see CBB section above)

---

## Odds API Setup
- **Env var**: `ODDS_API_KEY` (set in `.env` or deployment config)
- **Purpose**: Backfills spreads for games older than ~90 days (ESPN drops `pickcenter` data)
- **Cost**: $20/mo Rookie plan, 10 credits per historical request, 20K credits/month
- **Endpoint**: `GET /v4/historical/sports/{sport}/odds?apiKey={key}&regions=us&markets=spreads&date={iso_date}`

---

## Architecture Notes
- Rules replay engine reuses production scoring functions directly (no duplication)
- Team state tracked chronologically for B2B, H2H, ATS, vegas trap, trends
- MIN_WARMUP_GAMES = 10 (need some history before scoring is meaningful)
- Results stored in `tm_model_runs` table with `run_type = "rules_backtest"`
- Frontend "Rules Replay" tab shows factor breakdown, slot analysis, threshold sweep

---

## Edge Roadmap — All Improvements to Implement

### Tier 1: Quick Wins (Code Changes Only, No New Data)

#### CBB V2 Lean Flip + Signal Tuning
- **Flip vegas slot lean to favorite for CBB** — biggest single fix, vegas underdog lean is broken (39%)
- **Remove h2h_revenge for CBB** — 25% accuracy when it fires, actively harmful
- **Boost ats_record weight to +4-5** — strongest signal (70% when firing)
- **Add spread floor** — skip/downweight games with |spread| < 3 (coin flips at 53%)
- **Cap line movement magnitude scoring** — 1-3pt moves are gold (75-83%), 3+pt dilutes (57%)
- **Add ranked lean bonus (+2-3)** — lean team ranked #1-9 hits 81.2%
- **Expected lift**: Push CBB from 61.8% to ~67-70% on same volume

#### All Sports: Confidence Tier System
- Instead of just STRONG PLAY / LEAN / MONITOR, add a "factor count" qualifier
- If 3+ independent factors fire → boost confidence label
- If only slot_bonus fires → lower confidence even at high score
- Show "high confidence" vs "moderate confidence" in UI

### Tier 2: Missing Data Signals (Need API Integration)

#### Historical Injury Data (Trell Rule Replay)
- **Impact**: Trell Rule (+5) is currently zeroed out in all backtest games
- **APIs**: Sportradar, SportsData.io, MySportsFeeds
- **Storage**: `tm_historical_injuries` table (event_id, team, player, status, injury_date)
- **Benefit**: Enables Trell Rule replay, star player impact analysis, injury-adjusted scoring
- **Estimated lift**: +3-5% accuracy on games where star injuries matter

#### Historical Public Betting % (Sharp vs Public Money)
- **Impact**: Public betting factor (+3/+5) is zeroed out in all backtest games
- **APIs**: Action Network API, Pregame.com, historical Pinnacle odds via Odds API
- **Storage**: `tm_historical_betting` table (event_id, public_pct_home, sharp_spread, consensus_spread)
- **Benefit**: Validates whether sharp money divergence adds real edge
- **Estimated lift**: +2-4% accuracy when sharp/public diverge

#### Historical NFL Weather
- **Impact**: Weather factor (+5) can't be replayed for NFL backtest
- **APIs**: OpenWeather historical, Visual Crossing, Weather API
- **Storage**: Store with game record (temp, wind, precip, condition)
- **Benefit**: Validates weather impact on scoring + covers

### Tier 3: New Signals (Research + Build)

#### Conference Game Detection
- **Idea**: Conference games play differently than non-conference (more familiarity, tighter spreads)
- **Implementation**: Map teams to conferences via ESPN API, flag conf vs non-conf
- **Data needed**: ESPN team detail endpoint has `groups` (conference info)
- **Potential factor**: +2/-2 based on whether conf games cover differently

#### Pace of Play / Tempo Factor
- **Idea**: Fast-tempo teams in high-total games tend to go over; slow-tempo mismatches create variance
- **Implementation**: Track possessions per game or pace rating from ESPN advanced stats
- **Potential use**: Adjust game total expectations, flag O/U leans

#### Rest Days (Beyond B2B)
- **Idea**: 3+ days rest vs opponent with 1-day rest could be stronger signal than just B2B
- **Implementation**: Check schedule gap for both teams, score the differential
- **Potential factor**: +2 for 3+ day rest advantage, +4 for 4+ day gap

#### Home Court Strength Index (CBB)
- **Idea**: College home court advantage varies wildly (Cameron Indoor vs neutral-site-feeling arenas)
- **Implementation**: Track home win % per venue from historical data
- **Potential factor**: +2 for elite home court (>75% home win rate), -1 for weak (<55%)

#### Time Zone Travel Factor
- **Idea**: West Coast teams playing early East Coast games, or vice versa, may underperform
- **Implementation**: Map team time zones, flag 2+ zone travel for early games
- **Potential factor**: +1/-1 based on travel direction + game start time

#### Referee Tendencies (NBA/CBB)
- **Idea**: Some ref crews call more fouls → more free throws → favorites cover more
- **Implementation**: Would need referee assignment data (NBA ref API or manual)
- **Storage**: Historical ref crew → game outcome data
- **Potential factor**: +1/-1 based on ref crew ATS tendencies

### Tier 4: ML Enhancement (After More Data)

#### Gradient Boosted Model Layer
- **Idea**: Use the rules-based score as one feature, add all raw factor values + game context as features, train XGBoost/LightGBM
- **Requires**: 2000+ graded games per sport minimum
- **Benefit**: Can learn non-linear interactions between factors the rules engine misses
- **Implementation**: `test_model/ml_model.py` — train on historical, predict on live, compare to rules

#### Feature Importance Analysis
- **Idea**: Let the ML model rank which features actually matter per sport
- **Benefit**: Data-driven weight discovery instead of manual tuning
- **Potential**: Discover interactions we never thought to check (e.g., "rank scam + B2B + public slot" combo)

---

## Priority Order for Implementation
1. **CBB V2 tuning** (lean flip + signal boosts) — biggest immediate ROI, code only
2. **Historical injury API** — unlocks Trell Rule for all sports' backtests
3. **Confidence tier system** — better pick quality communication to user
4. **NHL/NFL/CFB data collection + tuning** — each sport needs its own backtest cycle
5. **Conference game detection** — low-hanging fruit for CBB/CFB
6. **Historical public betting** — validates sharp money signal
7. **ML model layer** — after 2000+ games collected per sport
