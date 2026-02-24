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
- [ ] **CBB** — Same process (shares rank logic with CFB, basketball-calibrated spreads)

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
