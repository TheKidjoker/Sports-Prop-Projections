import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Zap, RefreshCw, BarChart3, Target, AlertTriangle, Cloud, Users, Clock, Plus,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { approvePick, rejectPick } from "@/lib/api";
import type { PickData, Tier, SportLower } from "@/lib/types";
import type { BetSlipItem } from "@/components/bets/BetSlip";

export type { PickData, Tier };

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  rest: RefreshCw,
  chart: BarChart3,
  target: Target,
  alert: AlertTriangle,
  cloud: Cloud,
  users: Users,
  clock: Clock,
  zap: Zap,
};

const tierBadgeVariant: Record<Tier, "strong" | "confident" | "lean" | "monitor"> = {
  "STRONG PLAY": "strong",
  CONFIDENT: "confident",
  LEAN: "lean",
  MONITOR: "monitor",
};

const tierBorderClass: Record<Tier, string> = {
  "STRONG PLAY": "border-l-tier-strong",
  CONFIDENT: "border-l-tier-confident",
  LEAN: "border-l-tier-lean",
  MONITOR: "border-l-tier-monitor",
};

interface PickCardProps {
  pick: PickData;
  index: number;
  isAdmin?: boolean;
  onTrackBet?: (bet: BetSlipItem) => void;
}

export function PickCard({ pick, index, isAdmin = false, onTrackBet }: PickCardProps) {
  const badgeVariant = tierBadgeVariant[pick.tier] ?? "monitor";
  const borderClass = tierBorderClass[pick.tier] ?? "border-l-tier-monitor";
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
    } catch (e) {
      console.error("Approve failed:", e);
      setApproveState("idle");
    }
  };

  const handleReject = async () => {
    if (!pick.eventId || !pick.sport || rejectState !== "idle") return;
    setRejectState("loading");
    try {
      await rejectPick(pick.eventId, pick.sport as SportLower);
      setRejectState("done");
      queryClient.invalidateQueries({ queryKey: ["pending-picks"] });
      queryClient.invalidateQueries({ queryKey: ["scan", pick.sport] });
    } catch (e) {
      console.error("Reject failed:", e);
      setRejectState("idle");
    }
  };

  const handleTrack = () => {
    if (!onTrackBet || !pick.eventId || !pick.sport) return;
    // Parse spread number from spreadLine (e.g. "Lakers +6.5" → 6.5)
    const spreadMatch = pick.spreadLine.match(/([+-]?\d+\.?\d*)/);
    const line = spreadMatch ? parseFloat(spreadMatch[1]) : 0;
    onTrackBet({
      event_id: pick.eventId,
      sport: pick.sport,
      type: "spread",
      team: pick.spreadLine.split(/\s[+-]/)[0] || pick.awayTeam,
      line,
      label: `${pick.awayTeam} @ ${pick.homeTeam} — ${pick.spreadLine}`,
      home_team: pick.homeTeam,
      away_team: pick.awayTeam,
      recommendation: pick.tier,
      cover_pct: pick.coverPct,
      slot_type: pick.slotType,
      action: pick.actionString,
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.35 }}
      className={`card-surface rounded-sm ${borderClass} transition-all duration-200 group hover:translate-y-[-1px] hover:shadow-[0_8px_24px_-8px_hsla(0,72%,51%,0.15)]`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between px-3 sm:px-4 pt-3 pb-2">
        <Badge variant={badgeVariant}>
          {pick.tier}
        </Badge>
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm text-foreground">
            {pick.coverPct.toFixed(1)}%
          </span>
          <span className="text-[10px] text-muted-foreground font-mono">
            score:{pick.compositeScore}
          </span>
        </div>
      </div>

      {/* Matchup */}
      <div className="px-3 sm:px-4 pb-2">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-0.5">
          <span className="font-heading text-base sm:text-lg tracking-wider text-foreground">
            {pick.awayTeam}{" "}
            <span className="text-muted-foreground text-sm">@</span>{" "}
            {pick.homeTeam}
          </span>
          <div className="flex items-center gap-2 text-right">
            <span className="text-xs text-muted-foreground">{pick.gameTime}</span>
            {pick.slotType && (
              <span className="text-[10px] text-muted-foreground">{pick.slotType}</span>
            )}
          </div>
        </div>
        {pick.spreadLine && (
          <p className="text-xs text-muted-foreground">{pick.spreadLine}</p>
        )}
      </div>

      {/* Action string */}
      <div className="px-3 sm:px-4 py-2 border-t border-b border-border/50 bg-muted/20">
        {pick.actionString ? (
          <p className="text-xs sm:text-sm text-foreground font-medium leading-snug">&ldquo;{pick.actionString}&rdquo;</p>
        ) : pick.spreadLine ? (
          <p className="text-xs sm:text-sm text-foreground font-medium leading-snug">
            {pick.tier !== "MONITOR" ? `${pick.tier}: ` : ""}Lean {pick.spreadLine} — {pick.coverPct.toFixed(1)}% confidence
          </p>
        ) : (
          <p className="text-xs text-muted-foreground italic">
            Spread not yet available — {pick.coverPct.toFixed(1)}% model confidence
          </p>
        )}
      </div>

      {/* Factor pills */}
      <div className="px-3 sm:px-4 py-2.5 sm:py-3 flex flex-wrap gap-1.5 sm:gap-2">
        {pick.factors.map((factor, i) => {
          const IconComponent = iconMap[factor.icon];
          return (
            <span
              key={i}
              className={`inline-flex items-center gap-1 px-2 py-1 rounded-sm text-[10px] font-mono border ${
                factor.points > 0
                  ? "bg-success/10 text-success border-success/20"
                  : factor.points < 0
                  ? "bg-primary/10 text-primary border-primary/20"
                  : "bg-muted text-muted-foreground border-border"
              }`}
            >
              {IconComponent ? (
                <IconComponent className="w-2.5 h-2.5" />
              ) : (
                factor.icon
              )}{" "}
              {factor.label}
              {factor.unvalidated && <Zap className="w-2.5 h-2.5 text-warning" />}
              <span className="font-semibold">
                {factor.points > 0 ? "+" : ""}
                {factor.points}
              </span>
            </span>
          );
        })}
      </div>

      {/* Footer */}
      <div className="px-3 sm:px-4 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {pick.moneyline && (
            <span className="text-[10px] font-mono text-muted-foreground">
              ML: {pick.moneyline}
            </span>
          )}
          {pick.hasUnvalidated && (
            <span className="text-[10px] text-warning flex items-center gap-1">
              <Zap className="w-3 h-3" /> Includes unvalidated
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          {onTrackBet && pick.eventId && (
            <button
              onClick={handleTrack}
              className="px-2 py-1 text-[10px] font-heading bg-secondary/15 text-secondary border border-secondary/30 rounded-sm hover:bg-secondary/25 transition-colors flex items-center gap-1"
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
              <button
                onClick={handleApprove}
                disabled={approveState === "loading" || rejectState === "loading"}
                className="px-2 py-1 text-[10px] font-heading bg-success/15 text-success border border-success/30 rounded-sm hover:bg-success/25 transition-colors disabled:opacity-50"
              >
                {approveState === "loading" ? "..." : "APPROVE"}
              </button>
              <button
                onClick={handleReject}
                disabled={approveState === "loading" || rejectState === "loading"}
                className="px-2 py-1 text-[10px] font-heading bg-primary/15 text-primary border border-primary/30 rounded-sm hover:bg-primary/25 transition-colors disabled:opacity-50"
              >
                {rejectState === "loading" ? "..." : "REJECT"}
              </button>
            </>
          ) : null}
        </div>
      </div>
    </motion.div>
  );
}
