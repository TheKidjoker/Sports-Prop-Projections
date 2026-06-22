import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Zap, RefreshCw, BarChart3, Target, AlertTriangle, Cloud, Users, Clock, Plus,
} from "lucide-react";
import { approvePick, rejectPick } from "@/lib/api";
import { GaugeRing } from "@/components/jarvis/GaugeRing";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { CHART_COLORS } from "@/lib/chart-theme";
import type { PickData, Tier, SportLower } from "@/lib/types";
import type { BetSlipItem } from "@/components/bets/BetSlip";

export type { PickData, Tier };

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  rest: RefreshCw, chart: BarChart3, target: Target, alert: AlertTriangle,
  cloud: Cloud, users: Users, clock: Clock, zap: Zap,
};

const tierColors: Record<Tier, string> = {
  "STRONG PLAY": CHART_COLORS.crimson,
  CONFIDENT: CHART_COLORS.gold,
  LEAN: CHART_COLORS.foreground,
  MONITOR: CHART_COLORS.muted,
};

interface PickCardProps {
  pick: PickData;
  index: number;
  isAdmin?: boolean;
  onTrackBet?: (bet: BetSlipItem) => void;
}

export function PickCard({ pick, index, isAdmin = false, onTrackBet }: PickCardProps) {
  const color = tierColors[pick.tier] ?? CHART_COLORS.muted;
  const queryClient = useQueryClient();
  const [approveState, setApproveState] = useState<"idle" | "loading" | "done">("idle");
  const [rejectState, setRejectState] = useState<"idle" | "loading" | "done">("idle");

  const handleApprove = async () => {
    if (!pick.eventId || !pick.sport || approveState !== "idle") return;
    setApproveState("loading");
    try {
      await approvePick(pick.eventId, pick.sport as SportLower);
      setApproveState("done");
      queryClient.invalidateQueries({ queryKey: ["pending-picks"] });
      queryClient.invalidateQueries({ queryKey: ["scan", pick.sport] });
    } catch { setApproveState("idle"); }
  };

  const handleReject = async () => {
    if (!pick.eventId || !pick.sport || rejectState !== "idle") return;
    setRejectState("loading");
    try {
      await rejectPick(pick.eventId, pick.sport as SportLower);
      setRejectState("done");
      queryClient.invalidateQueries({ queryKey: ["pending-picks"] });
      queryClient.invalidateQueries({ queryKey: ["scan", pick.sport] });
    } catch { setRejectState("idle"); }
  };

  const handleTrack = () => {
    if (!onTrackBet || !pick.eventId || !pick.sport) return;
    const spreadMatch = pick.spreadLine.match(/([+-]?\d+\.?\d*)/);
    const line = spreadMatch ? parseFloat(spreadMatch[1]) : 0;
    onTrackBet({
      event_id: pick.eventId, sport: pick.sport, type: "spread",
      team: pick.spreadLine.split(/\s[+-]/)[0] || pick.awayTeam, line,
      label: `${pick.awayTeam} @ ${pick.homeTeam} — ${pick.spreadLine}`,
      home_team: pick.homeTeam, away_team: pick.awayTeam,
      recommendation: pick.tier, cover_pct: pick.coverPct,
      slot_type: pick.slotType, action: pick.actionString,
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className="hud-panel group transition-all duration-200 hover:translate-y-[-2px]"
      style={{ borderLeftWidth: 3, borderLeftColor: color, borderLeftStyle: "solid" }}
    >
      {/* Header: Tier badge + Confidence gauge */}
      <div className="flex items-center justify-between px-3 sm:px-4 pt-3 pb-2">
        <HexBadge label={pick.tier} color={color} size="md" active />
        <div className="flex items-center gap-3">
          <span className="font-mono text-[10px] text-muted-foreground">score:{pick.compositeScore}</span>
          <GaugeRing value={pick.coverPct} max={100} label="" unit="%" size={48} color={color} />
        </div>
      </div>

      {/* Matchup */}
      <div className="px-3 sm:px-4 pb-2">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-0.5">
          <span className="font-heading text-base sm:text-lg tracking-wider text-foreground">
            {pick.awayTeam} <span className="text-muted-foreground text-sm">@</span> {pick.homeTeam}
          </span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground">{pick.gameTime}</span>
            {pick.slotType && <span className="text-[10px] text-muted-foreground">{pick.slotType}</span>}
          </div>
        </div>
        {pick.spreadLine && (
          <p className="font-mono-nums text-sm text-foreground mt-0.5">
            {pick.spreadLine}
            {pick.bestLine && pick.bestLine.spread !== undefined && (
              <span className="ml-2 inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-mono" style={{ background: `${CHART_COLORS.green}15`, color: CHART_COLORS.green, border: `1px solid ${CHART_COLORS.green}30` }}>
                Best: {pick.bestLine.book} {pick.bestLine.spread > 0 ? "+" : ""}{pick.bestLine.spread}
                {pick.bestLine.spread_odds ? ` ${pick.bestLine.spread_odds}` : ""}
              </span>
            )}
          </p>
        )}
      </div>

      {/* Action string */}
      <div className="mx-3 sm:mx-4 py-2 mb-2" style={{ borderLeft: `2px solid ${color}`, paddingLeft: 12, background: "hsla(240,15%,7%,0.5)" }}>
        {pick.actionString ? (
          <p className="text-xs sm:text-sm text-foreground font-medium leading-snug">&ldquo;{pick.actionString}&rdquo;</p>
        ) : pick.spreadLine ? (
          <p className="text-xs sm:text-sm text-foreground font-medium leading-snug">
            {pick.tier !== "MONITOR" ? `${pick.tier}: ` : ""}Lean {pick.spreadLine} — {pick.coverPct.toFixed(1)}% confidence
          </p>
        ) : (
          <p className="text-xs text-muted-foreground italic">Spread not yet available — {pick.coverPct.toFixed(1)}% model confidence</p>
        )}
      </div>

      {/* Factor pills */}
      <div className="px-3 sm:px-4 py-2 flex flex-wrap gap-1.5">
        {pick.factors.map((factor, i) => {
          const IconComponent = iconMap[factor.icon];
          const isPositive = factor.points > 0;
          const isNegative = factor.points < 0;
          return (
            <span
              key={i}
              className="inline-flex items-center gap-1 px-2 py-1 text-[10px] font-mono border transition-all"
              style={{
                background: isPositive ? `${CHART_COLORS.green}15` : isNegative ? `${CHART_COLORS.crimson}15` : "hsla(240,10%,12%,1)",
                color: isPositive ? CHART_COLORS.green : isNegative ? CHART_COLORS.crimson : CHART_COLORS.muted,
                borderColor: isPositive ? `${CHART_COLORS.green}30` : isNegative ? `${CHART_COLORS.crimson}30` : "hsla(0,30%,12%,0.6)",
                boxShadow: isPositive ? `0 0 6px ${CHART_COLORS.green}20` : "none",
                clipPath: "polygon(4px 0, calc(100% - 4px) 0, 100% 50%, calc(100% - 4px) 100%, 4px 100%, 0 50%)",
              }}
            >
              {IconComponent ? <IconComponent className="w-2.5 h-2.5" /> : factor.icon}
              {" "}{factor.label}
              {factor.unvalidated && <Zap className="w-2.5 h-2.5 text-warning" />}
              <span className="font-semibold">{factor.points > 0 ? "+" : ""}{factor.points}</span>
            </span>
          );
        })}
      </div>

      {/* Footer */}
      <div className="px-3 sm:px-4 pb-3 pt-1 flex items-center justify-between border-t border-border/30">
        <div className="flex items-center gap-3">
          {pick.moneyline && <span className="text-[10px] font-mono text-muted-foreground">ML: {pick.moneyline}</span>}
          {pick.hasUnvalidated && (
            <span className="text-[10px] text-warning flex items-center gap-1"><Zap className="w-3 h-3" /> Unvalidated</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {onTrackBet && pick.eventId && (
            <button
              onClick={handleTrack}
              className="px-3 py-1 text-[10px] font-heading tracking-wider text-secondary border border-secondary/30 hover:bg-secondary/15 transition-colors flex items-center gap-1"
              style={{ clipPath: "polygon(4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px), 0 4px)" }}
            >
              <Plus className="w-2.5 h-2.5" /> TRACK
            </button>
          )}
          {isAdmin && rejectState === "done" ? (
            <span className="text-[10px] font-heading text-primary tracking-wider">REJECTED</span>
          ) : isAdmin && approveState === "done" ? (
            <span className="text-[10px] font-heading text-success tracking-wider">APPROVED</span>
          ) : isAdmin ? (
            <>
              <button onClick={handleApprove} disabled={approveState === "loading" || rejectState === "loading"} className="px-2 py-1 text-[10px] font-heading bg-success/15 text-success border border-success/30 hover:bg-success/25 transition-colors disabled:opacity-50">
                {approveState === "loading" ? "..." : "APPROVE"}
              </button>
              <button onClick={handleReject} disabled={approveState === "loading" || rejectState === "loading"} className="px-2 py-1 text-[10px] font-heading bg-primary/15 text-primary border border-primary/30 hover:bg-primary/25 transition-colors disabled:opacity-50">
                {rejectState === "loading" ? "..." : "REJECT"}
              </button>
            </>
          ) : null}
        </div>
      </div>
    </motion.div>
  );
}
