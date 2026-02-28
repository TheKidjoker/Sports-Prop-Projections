import { motion } from "framer-motion";
import {
  Zap, RefreshCw, BarChart3, Target, AlertTriangle, Cloud, Users, Clock, Plus,
} from "lucide-react";
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

const tierConfig: Record<Tier, { className: string; borderClass: string }> = {
  "STRONG PLAY": {
    className: "bg-primary/20 text-primary border-primary/40",
    borderClass: "border-l-tier-strong",
  },
  CONFIDENT: {
    className: "bg-secondary/20 text-secondary border-secondary/40",
    borderClass: "border-l-tier-confident",
  },
  LEAN: {
    className: "bg-foreground/10 text-foreground border-foreground/20",
    borderClass: "border-l-tier-lean",
  },
  MONITOR: {
    className: "bg-muted-foreground/10 text-muted-foreground border-muted-foreground/20",
    borderClass: "border-l-tier-monitor",
  },
};

interface PickCardProps {
  pick: PickData;
  index: number;
  isAdmin?: boolean;
  onTrackBet?: (bet: BetSlipItem) => void;
}

export function PickCard({ pick, index, isAdmin = false, onTrackBet }: PickCardProps) {
  const config = tierConfig[pick.tier] ?? tierConfig.MONITOR;

  const handleApprove = async () => {
    if (!pick.eventId || !pick.sport) return;
    try {
      await approvePick(pick.eventId, pick.sport as SportLower);
    } catch (e) {
      console.error("Approve failed:", e);
    }
  };

  const handleReject = async () => {
    if (!pick.eventId || !pick.sport) return;
    try {
      await rejectPick(pick.eventId, pick.sport as SportLower);
    } catch (e) {
      console.error("Reject failed:", e);
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
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.35 }}
      className={`card-surface rounded-sm ${config.borderClass} transition-all duration-200 group hover:translate-y-[-1px] hover:shadow-[0_8px_24px_-8px_hsla(0,72%,51%,0.15)]`}
    >
      {/* Header row */}
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <span className={`text-[10px] font-heading tracking-wider px-2 py-0.5 border rounded-sm ${config.className}`}>
          {pick.tier}
        </span>
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
      <div className="px-4 pb-2">
        <div className="flex items-center justify-between">
          <span className="font-heading text-lg tracking-wider text-foreground">
            {pick.awayTeam}{" "}
            <span className="text-muted-foreground text-sm">@</span>{" "}
            {pick.homeTeam}
          </span>
          <div className="text-right">
            <span className="text-xs text-muted-foreground">{pick.gameTime}</span>
            {pick.slotType && (
              <span className="text-[10px] text-muted-foreground ml-2">{pick.slotType}</span>
            )}
          </div>
        </div>
        {pick.spreadLine && (
          <p className="text-xs text-muted-foreground">{pick.spreadLine}</p>
        )}
      </div>

      {/* Action string */}
      <div className="px-4 py-2 border-t border-b border-border/50 bg-muted/20">
        {pick.actionString ? (
          <p className="text-sm text-foreground font-medium">&ldquo;{pick.actionString}&rdquo;</p>
        ) : pick.spreadLine ? (
          <p className="text-sm text-foreground font-medium">
            {pick.tier !== "MONITOR" ? `${pick.tier}: ` : ""}Lean {pick.spreadLine} — {pick.coverPct.toFixed(1)}% confidence
          </p>
        ) : (
          <p className="text-xs text-muted-foreground italic">
            Spread not yet available — {pick.coverPct.toFixed(1)}% model confidence
          </p>
        )}
      </div>

      {/* Factor pills */}
      <div className="px-4 py-3 flex flex-wrap gap-2">
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
      <div className="px-4 pb-3 flex items-center justify-between">
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
          {isAdmin && (
            <>
              <button
                onClick={handleApprove}
                className="px-2 py-1 text-[10px] font-heading bg-success/15 text-success border border-success/30 rounded-sm hover:bg-success/25 transition-colors"
              >
                APPROVE
              </button>
              <button
                onClick={handleReject}
                className="px-2 py-1 text-[10px] font-heading bg-primary/15 text-primary border border-primary/30 rounded-sm hover:bg-primary/25 transition-colors"
              >
                REJECT
              </button>
            </>
          )}
        </div>
      </div>
    </motion.div>
  );
}
