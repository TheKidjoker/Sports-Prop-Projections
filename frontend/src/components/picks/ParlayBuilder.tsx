import { useState, useEffect } from "react";
import type { PickData, PropSignal, SportLower, ParlayAnalysis } from "@/lib/types";
import type { BetSlipItem } from "@/components/bets/BetSlip";
import { analyzeParlayCorrelation } from "@/lib/api";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { GaugeRing } from "@/components/jarvis/GaugeRing";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { CHART_COLORS } from "@/lib/chart-theme";

// ─── Types ────────────────────────────────────────────

export interface ParlayLeg {
  label: string;
  coverPct: number;
  sport: SportLower;
  type: "spread" | "prop";
  eventId?: string;
  team?: string;
  line?: number;
  homeTeam?: string;
  awayTeam?: string;
  recommendation?: string;
  action?: string;
  slotType?: string;
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
  nba: "hsl(43, 76%, 38%)",
  nhl: "hsl(200, 70%, 50%)",
  mlb: "hsl(0, 72%, 51%)",
  cbb: "hsl(30, 80%, 50%)",
  nfl: "hsl(142, 71%, 45%)",
  cfb: "hsl(280, 60%, 55%)",
  soccer: "hsl(120, 50%, 40%)",
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

function diversify(legs: ParlayLeg[], maxPerSport: number): ParlayLeg[] {
  const counts: Record<string, number> = {};
  return legs.filter((leg) => {
    counts[leg.sport] = (counts[leg.sport] || 0) + 1;
    return counts[leg.sport] <= maxPerSport;
  });
}

function distinctSports(legs: ParlayLeg[]): number {
  return new Set(legs.map((l) => l.sport)).size;
}

export function buildCrossSportParlays(
  picks: PickData[],
  props: (PropSignal & { _sport: SportLower })[]
): ParlayTier[] {
  const spreadLegs = picks.filter((p) => p.tier !== "MONITOR").map(makeLeg);
  const propLegs = props.filter((p) => p.signal === "STRONG" || p.signal === "LEAN").map(makePropLeg);
  const allLegs = [...spreadLegs, ...propLegs].sort((a, b) => b.coverPct - a.coverPct);

  const parlays: ParlayTier[] = [];

  const safeLegs = allLegs.filter((l) => l.coverPct >= 65).slice(0, 2);
  if (safeLegs.length === 2) {
    parlays.push({ name: "Two-Face's Safe Bet", subtitle: "2-leg parlay, highest confidence", legs: safeLegs, className: "border-success/30" });
  }

  const gambitPool = diversify(allLegs.filter((l) => l.coverPct >= 60), 2).slice(0, 6);
  if (gambitPool.length >= 4) {
    parlays.push({ name: "Gotham Gambit", subtitle: `${gambitPool.length}-leg parlay`, legs: gambitPool, className: "border-secondary/30" });
  }

  const breakoutPool = diversify(allLegs.filter((l) => l.coverPct >= 55), 3).slice(0, 10);
  if (breakoutPool.length >= 3) {
    parlays.push({ name: "Gotham Breakout", subtitle: `${breakoutPool.length}-leg longshot`, legs: breakoutPool, className: "border-primary/30" });
  }

  const bestLegs = allLegs.slice(0, 6);
  const bestDiverse: ParlayLeg[] = [];
  const bestCounts: Record<string, number> = {};
  for (const leg of bestLegs) {
    if (bestDiverse.length >= 3) break;
    bestCounts[leg.sport] = (bestCounts[leg.sport] || 0) + 1;
    if (bestCounts[leg.sport] <= 2) bestDiverse.push(leg);
  }
  if (bestDiverse.length >= 3 && distinctSports(bestDiverse) >= 2) {
    parlays.push({ name: "Best of Day", subtitle: "Top picks across sports", legs: bestDiverse, className: "border-accent/30" });
  }

  return parlays;
}

// ─── Convert parlay legs to BetSlipItems ──────────────

export function parlayLegsToSlipItems(legs: ParlayLeg[]): BetSlipItem[] {
  return legs.map((leg) => {
    if (leg.type === "prop") {
      return {
        event_id: leg.eventId ?? "", sport: leg.sport, type: "prop",
        team: leg.team ?? "", stat: leg.statType, line: leg.propLine ?? 0,
        label: leg.label, home_team: leg.homeTeam, away_team: leg.awayTeam,
        player_name: leg.playerName, direction: leg.direction,
        projection: leg.projection, edge: leg.edge, confidence: leg.coverPct, signal: leg.signal,
      };
    }
    return {
      event_id: leg.eventId ?? "", sport: leg.sport, type: "spread",
      team: leg.team ?? "", line: leg.line ?? 0, label: leg.label,
      home_team: leg.homeTeam, away_team: leg.awayTeam,
      recommendation: leg.recommendation, cover_pct: leg.coverPct,
      slot_type: leg.slotType, action: leg.action,
    };
  });
}

// ─── ParlayCard Component ─────────────────────────────

interface ParlayCardProps {
  parlay: ParlayTier;
  onTrackAll?: (items: BetSlipItem[]) => void;
}

export function ParlayCard({ parlay, onTrackAll }: ParlayCardProps) {
  const combinedProb = parlay.legs.reduce((acc, leg) => acc * (leg.coverPct / 100), 1);
  const [analysis, setAnalysis] = useState<ParlayAnalysis | null>(null);

  useEffect(() => {
    const legsPayload = parlay.legs.map((leg) => ({
      sport: leg.sport,
      stat_type: leg.statType ?? "SPREAD",
      coverPct: leg.coverPct,
    }));
    analyzeParlayCorrelation(legsPayload)
      .then((res) => { if (res.success) setAnalysis(res.analysis); })
      .catch(() => {});
  }, [parlay.legs.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const hasCorrelation = analysis && analysis.correlation_penalty_pct > 5;
  const adjustedProb = analysis?.adjusted_joint_prob;

  return (
    <HudPanel
      title={parlay.name}
      status={hasCorrelation ? "warning" : "online"}
      headerRight={
        hasCorrelation ? (
          <HexBadge label="CORRELATED" color={CHART_COLORS.gold} size="sm" active />
        ) : undefined
      }
      className={`border-l-2 ${parlay.className}`}
    >
      <p className="text-[13px] text-muted-foreground mb-3">{parlay.subtitle}</p>

      {/* Legs */}
      <div className="space-y-0">
        {parlay.legs.map((leg, i) => (
          <div key={i} className="flex items-center gap-2 py-1.5 border-b border-border/20 last:border-0">
            <HexBadge label={leg.sport.toUpperCase().slice(0, 3)} size="sm" active color={SPORT_COLORS[leg.sport]} />
            {leg.type === "prop" && (
              <span className="text-[11px] font-heading tracking-wider px-1 py-0.5 bg-secondary/15 text-secondary border border-secondary/30">
                {leg.statType ?? "PROP"}
              </span>
            )}
            <span className="font-mono text-[13px] text-foreground truncate flex-1">{leg.label}</span>
            <span className="font-mono text-[13px] text-success whitespace-nowrap">{leg.coverPct.toFixed(1)}%</span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="pt-3 mt-3 border-t border-border/30 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <GaugeRing
            value={combinedProb * 100}
            max={100}
            label="COMBINED"
            unit="%"
            size={48}
            color={combinedProb > 0.15 ? CHART_COLORS.green : CHART_COLORS.crimson}
          />
          {adjustedProb != null && adjustedProb !== combinedProb && (
            <div className="text-center">
              <span className="font-mono text-xs text-warning">{(adjustedProb * 100).toFixed(1)}%</span>
              <p className="text-[11px] font-heading tracking-wider text-muted-foreground">ADJUSTED</p>
            </div>
          )}
        </div>

        {onTrackAll && (
          <button
            onClick={() => onTrackAll(parlayLegsToSlipItems(parlay.legs))}
            className="px-4 py-1.5 text-[13px] font-heading tracking-wider bg-primary/15 text-primary border border-primary/30 hover:bg-primary/25 transition-colors"
            style={{ clipPath: "polygon(4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px), 0 4px)" }}
          >
            ADD TO BET SLIP
          </button>
        )}
      </div>

      {hasCorrelation && analysis.correlated_pairs.length > 0 && (
        <div className="mt-2 text-[12px] text-warning font-mono">
          Correlated: {analysis.correlated_pairs.map((p) => `${p.stat_a}+${p.stat_b} (${(p.correlation * 100).toFixed(0)}%)`).join(", ")}
          {" "} — penalty {analysis.correlation_penalty_pct.toFixed(1)}%
        </div>
      )}
    </HudPanel>
  );
}
