import type { PickData, PropSignal, SportLower } from "@/lib/types";
import type { BetSlipItem } from "@/components/bets/BetSlip";

// ─── Types ────────────────────────────────────────────

export interface ParlayLeg {
  label: string;
  coverPct: number;
  sport: SportLower;
  type: "spread" | "prop";
  // Spread metadata
  eventId?: string;
  team?: string;
  line?: number;
  homeTeam?: string;
  awayTeam?: string;
  recommendation?: string;
  action?: string;
  slotType?: string;
  // Prop metadata
  playerName?: string;
  statType?: string;
  propLine?: number;
  direction?: string;
  projection?: number;
  edge?: number;
  signal?: string;
}

export interface ParlayTier {
  name: string;
  subtitle: string;
  legs: ParlayLeg[];
  className: string;
}

// ─── Sport badge colors ───────────────────────────────

const SPORT_COLORS: Record<string, string> = {
  nba: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  nhl: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  cbb: "bg-purple-500/20 text-purple-400 border-purple-500/30",
  nfl: "bg-green-500/20 text-green-400 border-green-500/30",
  cfb: "bg-red-500/20 text-red-400 border-red-500/30",
};

// ─── Build parlays from cross-sport data ──────────────

function makeLeg(pick: PickData): ParlayLeg {
  return {
    label: `${pick.awayTeam} @ ${pick.homeTeam} — ${pick.spreadLine}`,
    coverPct: pick.coverPct,
    sport: pick.sport ?? "nba",
    type: "spread",
    eventId: pick.eventId,
    team: pick.spreadLine.split(" ")[0],
    line: pick.compositeScore,
    homeTeam: pick.homeTeam,
    awayTeam: pick.awayTeam,
    recommendation: pick.tier,
    action: pick.actionString,
    slotType: pick.slotType,
  };
}

function makePropLeg(prop: PropSignal & { _sport: SportLower }): ParlayLeg {
  const dir = prop.edge > 0 ? "OVER" : "UNDER";
  const dirLabel = dir === "OVER" ? "o" : "u";
  return {
    label: `${prop.player_name} ${prop.stat_type} ${dirLabel}${prop.line}`,
    coverPct: prop.confidence,
    sport: prop._sport,
    type: "prop",
    eventId: prop.event_id,
    team: prop.team,
    homeTeam: prop.is_home ? prop.team : prop.opponent,
    awayTeam: prop.is_home ? prop.opponent : prop.team,
    playerName: prop.player_name,
    statType: prop.stat_type,
    propLine: prop.line,
    direction: dir,
    projection: prop.projection,
    edge: prop.edge,
    signal: prop.signal,
  };
}

/** Diversify legs across sports: max N per sport */
function diversify(legs: ParlayLeg[], maxPerSport: number): ParlayLeg[] {
  const counts: Record<string, number> = {};
  return legs.filter((leg) => {
    counts[leg.sport] = (counts[leg.sport] || 0) + 1;
    return counts[leg.sport] <= maxPerSport;
  });
}

/** Count distinct sports in a set of legs */
function distinctSports(legs: ParlayLeg[]): number {
  return new Set(legs.map((l) => l.sport)).size;
}

export function buildCrossSportParlays(
  picks: PickData[],
  props: (PropSignal & { _sport: SportLower })[]
): ParlayTier[] {
  // Build all candidate legs
  const spreadLegs = picks
    .filter((p) => p.tier !== "MONITOR")
    .map(makeLeg);

  const propLegs = props
    .filter((p) => p.signal === "STRONG" || p.signal === "LEAN")
    .map(makePropLeg);

  const allLegs = [...spreadLegs, ...propLegs].sort(
    (a, b) => b.coverPct - a.coverPct
  );

  const parlays: ParlayTier[] = [];

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

  // Gotham Gambit: 4-6 legs >= 60%, max 2 per sport
  const gambitPool = diversify(
    allLegs.filter((l) => l.coverPct >= 60),
    2
  ).slice(0, 6);
  if (gambitPool.length >= 4) {
    parlays.push({
      name: "Gotham Gambit",
      subtitle: `${gambitPool.length}-leg parlay`,
      legs: gambitPool,
      className: "border-secondary/30",
    });
  }

  // Gotham Breakout: up to 10 legs >= 55%, max 3 per sport
  const breakoutPool = diversify(
    allLegs.filter((l) => l.coverPct >= 55),
    3
  ).slice(0, 10);
  if (breakoutPool.length >= 3) {
    parlays.push({
      name: "Gotham Breakout",
      subtitle: `${breakoutPool.length}-leg longshot`,
      legs: breakoutPool,
      className: "border-primary/30",
    });
  }

  // Best of Day: top 3 legs from >= 2 different sports
  const bestLegs = allLegs.slice(0, 6); // take top 6, filter to 3 with diversity
  const bestDiverse: ParlayLeg[] = [];
  const bestCounts: Record<string, number> = {};
  for (const leg of bestLegs) {
    if (bestDiverse.length >= 3) break;
    bestCounts[leg.sport] = (bestCounts[leg.sport] || 0) + 1;
    if (bestCounts[leg.sport] <= 2) {
      bestDiverse.push(leg);
    }
  }
  if (bestDiverse.length >= 3 && distinctSports(bestDiverse) >= 2) {
    parlays.push({
      name: "Best of Day",
      subtitle: "Top picks across sports",
      legs: bestDiverse,
      className: "border-accent/30",
    });
  }

  return parlays;
}

// ─── Convert parlay legs to BetSlipItems ──────────────

export function parlayLegsToSlipItems(legs: ParlayLeg[]): BetSlipItem[] {
  return legs.map((leg) => {
    if (leg.type === "prop") {
      return {
        event_id: leg.eventId ?? "",
        sport: leg.sport,
        type: "prop",
        team: leg.team ?? "",
        stat: leg.statType,
        line: leg.propLine ?? 0,
        label: leg.label,
        home_team: leg.homeTeam,
        away_team: leg.awayTeam,
        player_name: leg.playerName,
        direction: leg.direction,
        projection: leg.projection,
        edge: leg.edge,
        confidence: leg.coverPct,
        signal: leg.signal,
      };
    }
    return {
      event_id: leg.eventId ?? "",
      sport: leg.sport,
      type: "spread",
      team: leg.team ?? "",
      line: leg.line ?? 0,
      label: leg.label,
      home_team: leg.homeTeam,
      away_team: leg.awayTeam,
      recommendation: leg.recommendation,
      cover_pct: leg.coverPct,
      slot_type: leg.slotType,
      action: leg.action,
    };
  });
}

// ─── ParlayCard Component ─────────────────────────────

interface ParlayCardProps {
  parlay: ParlayTier;
  onTrackAll?: (items: BetSlipItem[]) => void;
}

export function ParlayCard({ parlay, onTrackAll }: ParlayCardProps) {
  const combinedProb = parlay.legs.reduce(
    (acc, leg) => acc * (leg.coverPct / 100),
    1
  );

  return (
    <div
      className={`card-surface rounded-sm border-l-2 ${parlay.className}`}
    >
      {/* Header */}
      <div className="px-4 pt-3 pb-2">
        <h4 className="font-heading text-sm tracking-wider text-foreground">
          {parlay.name}
        </h4>
        <p className="text-[10px] text-muted-foreground">{parlay.subtitle}</p>
      </div>

      {/* Legs */}
      <div className="px-4 pb-2">
        {parlay.legs.map((leg, i) => (
          <div
            key={i}
            className="flex items-center gap-2 py-1.5 border-b border-border/20 last:border-0"
          >
            {/* Sport badge */}
            <span
              className={`px-1.5 py-0.5 text-[8px] font-heading tracking-wider rounded border ${SPORT_COLORS[leg.sport] ?? "bg-muted text-muted-foreground border-border"}`}
            >
              {leg.sport.toUpperCase()}
            </span>

            {/* Type badge */}
            <span className={`text-[8px] font-heading tracking-wider w-8 text-center ${
              leg.type === "prop"
                ? "px-1 py-0.5 rounded-sm bg-secondary/15 text-secondary border border-secondary/30"
                : "text-muted-foreground"
            }`}>
              {leg.type === "spread" ? "SPR" : (leg.statType ?? "PROP")}
            </span>

            {/* Label */}
            <span className="font-mono text-[10px] text-foreground truncate flex-1">
              {leg.label}
            </span>

            {/* Confidence */}
            <span className="font-mono text-[10px] text-success whitespace-nowrap">
              {leg.coverPct.toFixed(1)}%
            </span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-border/30 flex items-center justify-between">
        <span className="text-[10px] font-heading tracking-wider text-muted-foreground">
          COMBINED:{" "}
          <span className="text-foreground">
            {(combinedProb * 100).toFixed(1)}%
          </span>
        </span>

        {onTrackAll && (
          <button
            onClick={() => onTrackAll(parlayLegsToSlipItems(parlay.legs))}
            className="px-3 py-1 text-[10px] font-heading tracking-wider bg-primary/15 text-primary border border-primary/30 rounded-sm hover:bg-primary/25 transition-colors"
          >
            TRACK ALL LEGS
          </button>
        )}
      </div>
    </div>
  );
}
