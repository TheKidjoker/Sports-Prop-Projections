import { motion } from "framer-motion";
import { Zap } from "lucide-react";

type Tier = "STRONG PLAY" | "CONFIDENT" | "LEAN" | "MONITOR";

interface Factor {
  label: string;
  icon: string;
  points: number;
  unvalidated?: boolean;
}

export interface PickData {
  id: string;
  tier: Tier;
  coverPct: number;
  compositeScore: number;
  awayTeam: string;
  homeTeam: string;
  gameTime: string;
  slotType: string;
  actionString: string;
  spreadLine: string;
  factors: Factor[];
  moneyline?: string;
  hasUnvalidated?: boolean;
}

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
}

export function PickCard({ pick, index, isAdmin = false }: PickCardProps) {
  const config = tierConfig[pick.tier];

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
            <span className="text-[10px] text-muted-foreground ml-2">{pick.slotType}</span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">{pick.spreadLine}</p>
      </div>

      {/* Action string */}
      <div className="px-4 py-2 border-t border-b border-border/50 bg-muted/20">
        <p className="text-sm text-foreground font-medium">&ldquo;{pick.actionString}&rdquo;</p>
      </div>

      {/* Factor pills */}
      <div className="px-4 py-3 flex flex-wrap gap-2">
        {pick.factors.map((factor, i) => (
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
            {factor.icon} {factor.label}
            {factor.unvalidated && <Zap className="w-2.5 h-2.5 text-warning" />}
            <span className="font-semibold">
              {factor.points > 0 ? "+" : ""}
              {factor.points}
            </span>
          </span>
        ))}
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

        {isAdmin && (
          <div className="flex items-center gap-1">
            <button className="px-2 py-1 text-[10px] font-heading bg-success/15 text-success border border-success/30 rounded-sm hover:bg-success/25 transition-colors">
              ✓ APPROVE
            </button>
            <button className="px-2 py-1 text-[10px] font-heading bg-primary/15 text-primary border border-primary/30 rounded-sm hover:bg-primary/25 transition-colors">
              ✗ REJECT
            </button>
            <button className="px-2 py-1 text-[10px] font-heading bg-secondary/15 text-secondary border border-secondary/30 rounded-sm hover:bg-secondary/25 transition-colors">
              👁 WATCH
            </button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
