# The Sharp Edge

A rules-based sports betting analysis engine that evaluates spread plays across **NBA**, **NHL**, **CFB**, and **NFL** using time-slot theory, line movement, injury impact, and sport-specific signals.

## How It Works

Not all time slots are created equal. Vegas adjusts its edge depending on when games are played. This tool classifies every game into a slot type, then layers additional confirmation factors on top to produce a confidence score.

## Glossary

### Slot Types

| Term | Meaning |
|------|---------|
| **Public** | A time slot where the sensible, publicly-expected outcome tends to hit. Lean with the favorite. |
| **Vegas** | A time slot where the books hold the edge and sharp money dominates. Lean with the underdog. |
| **Trap** | A game designed to look appealing but likely to burn public bettors. Fade the obvious pick. |
| **Skip** | A game that should not be bet at all (e.g., Sunday Night Football). |

### Confirmation Factors

| Term | Meaning |
|------|---------|
| **Line Movement** | The spread shifted between open and close. If the movement direction matches the slot type, it confirms the play. |
| **Trell Rule** | A star player is ruled Out with a recent injury in a Vegas slot. The absence creates exploitable value. |
| **Rank Scam** | (CFB) A higher-ranked team is at home but listed as the underdog against a lower-ranked opponent. |
| **Spread Discrepancy** | (CFB) The actual spread is significantly lower than expected for a ranked team's tier. |
| **Trend Discrepancy** | (NFL) One or both teams' last 4 games show a lopsided record, signaling bounce-back value or regression risk. |
| **O/U Alert** | (NFL) The over/under total is unusually high or diverges significantly from the teams' recent scoring averages. |
| **Weather Alert** | (NFL) Extreme outdoor conditions (high wind, freezing temp, precipitation) that can affect scoring. |
| **Dome** | (NFL) The game is played in an indoor stadium. Weather does not apply. |

### Recommendation Labels

| Label | Meaning |
|-------|---------|
| **STRONG PLAY** | Multiple confirmation factors align. Highest conviction. |
| **LEAN** | Some factors confirm. Worth a look. |
| **MONITOR** | Limited confirmation. Watch but don't commit. |

### Other Terms

| Term | Meaning |
|------|---------|
| **Cover %** | The model's estimated likelihood that the recommended side covers the spread. |
| **Moneyline** | When the spread is 3+ points, the tool suggests taking the moneyline instead of the spread. |
| **Quick Generate** | Scans all of today's games at once and ranks them by confidence. |
| **Parlay Suggestions** | Auto-generated multi-leg bet combinations built from the day's highest-confidence plays. |

## Sports Supported

- **NBA** — Time-slot classification with day-of-week rules and first-game override
- **NHL** — Slate-size-based classification (1 game, 2 games, 3+ time-based)
- **CFB** — Day overrides + Saturday time slots, rank scam and spread discrepancy detection
- **NFL** — Day overrides + Sunday early/late/night slots, trend discrepancy, O/U analysis, live weather

## Usage

```
python app.py
```

Open `http://localhost:5000` in your browser. Select a sport, hit Quick Generate, or use the manual form.
