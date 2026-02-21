# Sports Prop Projections

A rules-based player prop projection engine for NBA and college basketball that evaluates over/under likelihoods using recent performance metrics and contextual factors.

## Core Betting Theory

This tool is built around a key concept: **not all time slots are created equal**.

### Public Days
There are specific days and times where Vegas is more likely to let the public win. These windows tend to favor straightforward, stats-backed bets. When the model detects a Public Day, it leans into player averages and historical cover rates with higher confidence.

### Vegas Slots
On the flip side, there are days and times where Vegas holds the edge. During these windows, the books are more aggressive with their lines, and the public is more likely to lose. When the model detects a Vegas Slot, it adjusts its confidence accordingly and may recommend passing on bets that would otherwise look favorable.

### Monday Time Slots (PST)

| Time (PST) | Slot Type |
|------------|-----------|
| 5:00 PM    | Vegas     |
| 6:00 PM    | Public    |
| 7:00 PM    | Vegas     |
| 7:30 PM    | Public    |
| 9:00 PM    | Vegas     |
| 10:00 PM   | Public    |

### Why This Matters
Most projection tools treat every game the same regardless of when it's played. By factoring in **when** a bet is placed — not just the stats behind it — this tool aims to add a layer of context that pure numbers miss.

## Project Structure

- `main.py` — Entry point. Collects user input and runs predictions.
- `projections.py` — Prediction logic (Over/Under/Pass) and historical cover rate calculations.
- `time_slots.py` — Classifies game day + time into Public Day or Vegas Slot.
- `api_client.py` — Fetches real NBA player data from the balldontlie API.

## Usage

```
python main.py
```

You will be prompted for:
1. Player name (e.g., LeBron James)
2. Vegas points line
3. Number of recent games to analyze

The tool outputs a directional prediction with confidence and historical cover rates against the given line.
