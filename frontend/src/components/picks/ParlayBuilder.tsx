import type { PickData, PropSignal } from "@/lib/types";

interface ParlayLeg {
  label: string;
  coverPct: number;
}

interface Parlay {
  name: string;
  subtitle: string;
  legs: ParlayLeg[];
  className: string;
}

function buildParlays(picks: PickData[], props: PropSignal[]): Parlay[] {
  // Combine pick legs and prop legs
  const allLegs: ParlayLeg[] = [
    ...picks.map((p) => ({
      label: `${p.awayTeam} @ ${p.homeTeam} — ${p.spreadLine}`,
      coverPct: p.coverPct,
    })),
    ...props
      .filter((p) => p.signal === "STRONG")
      .map((p) => ({
        label: `${p.player_name} ${p.stat} o${p.line}`,
        coverPct: p.confidence,
      })),
  ].sort((a, b) => b.coverPct - a.coverPct);

  const parlays: Parlay[] = [];

  // Two-Face's Safe Bet: top 2 legs >= 65%
  const safeLegs = allLegs.filter((l) => l.coverPct >= 65).slice(0, 2);
  if (safeLegs.length === 2) {
    parlays.push({
      name: "Two-Face's Safe Bet",
      subtitle: "2-leg parlay, highest confidence",
      legs: safeLegs,
      className: "border-success/30",
    });
  }

  // Gotham Gambit: 4-6 legs >= 60%
  const gambitLegs = allLegs.filter((l) => l.coverPct >= 60).slice(0, 6);
  if (gambitLegs.length >= 4) {
    parlays.push({
      name: "Gotham Gambit",
      subtitle: `${gambitLegs.length}-leg parlay`,
      legs: gambitLegs,
      className: "border-secondary/30",
    });
  }

  // Gotham Breakout: up to 10 legs >= 55%
  const breakoutLegs = allLegs.filter((l) => l.coverPct >= 55).slice(0, 10);
  if (breakoutLegs.length >= 3) {
    parlays.push({
      name: "Gotham Breakout",
      subtitle: `${breakoutLegs.length}-leg longshot`,
      legs: breakoutLegs,
      className: "border-primary/30",
    });
  }

  return parlays;
}

interface ParlayBuilderProps {
  picks: PickData[];
  props: PropSignal[];
}

export function ParlayBuilder({ picks, props }: ParlayBuilderProps) {
  const parlays = buildParlays(picks, props);

  if (parlays.length === 0) return null;

  return (
    <div className="py-6 px-6 max-w-5xl mx-auto">
      <h3 className="font-heading text-xs tracking-[0.2em] text-primary mb-4">
        PARLAY SUGGESTIONS
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {parlays.map((parlay) => (
          <div key={parlay.name} className={`card-surface rounded-sm border-l-2 ${parlay.className}`}>
            <div className="px-4 pt-3 pb-2">
              <h4 className="font-heading text-sm tracking-wider text-foreground">
                {parlay.name}
              </h4>
              <p className="text-[10px] text-muted-foreground">{parlay.subtitle}</p>
            </div>
            <div className="px-4 pb-3">
              {parlay.legs.map((leg, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between py-1 border-b border-border/20 last:border-0"
                >
                  <span className="font-mono text-[10px] text-foreground truncate pr-2">
                    {leg.label}
                  </span>
                  <span className="font-mono text-[10px] text-success whitespace-nowrap">
                    {leg.coverPct.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
