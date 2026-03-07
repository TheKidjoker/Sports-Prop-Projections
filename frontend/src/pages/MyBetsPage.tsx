import { useState, useEffect, useRef } from "react";
import { Trash2 } from "lucide-react";
import { useGradeBets, useDeleteBet, useBetsCombined } from "@/hooks/use-bets";
import { toLowerSport, type Sport, type TrackedBet } from "@/lib/types";
import { toast } from "sonner";

interface MyBetsPageProps {
  sport: Sport | null;
}

const resultBadge = (result: string) => {
  switch (result) {
    case "WIN":
      return "bg-success/15 text-success border-success/30";
    case "LOSS":
      return "bg-primary/15 text-primary border-primary/30";
    case "PUSH":
      return "bg-warning/15 text-warning border-warning/30";
    default:
      return "bg-muted text-muted-foreground border-border";
  }
};

const recBadge = (rec: string | null | undefined) => {
  if (!rec) return null;
  if (rec === "STRONG PLAY") return "bg-primary/15 text-primary border-primary/30";
  if (rec === "CONFIDENT") return "bg-secondary/15 text-secondary border-secondary/30";
  return "bg-foreground/10 text-foreground border-foreground/20";
};

function BetLine({ bet }: { bet: TrackedBet }) {
  const isSpread = bet.bet_type === "spread";
  const isProp = bet.bet_type === "prop";

  return (
    <div className="flex items-start sm:items-center justify-between px-4 py-3 border-b border-border/30 hover:bg-muted/20 gap-2">
      <div className="flex-1 min-w-0">
        {/* Row 1: Sport badge + matchup */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-heading text-muted-foreground uppercase shrink-0">
            {bet.sport}
          </span>
          <span className="font-mono text-xs text-foreground truncate">
            {bet.away_team} @ {bet.home_team}
          </span>
          {bet.recommendation && (
            <span className={`text-[9px] font-heading px-1.5 py-0.5 border rounded-sm shrink-0 ${recBadge(bet.recommendation)}`}>
              {bet.recommendation}
            </span>
          )}
        </div>

        {/* Row 2: Pick details */}
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {isSpread && bet.lean_team && (
            <span className="font-mono text-xs text-secondary">
              {bet.lean_team} {bet.spread_at_pick != null ? (bet.spread_at_pick > 0 ? `+${bet.spread_at_pick}` : bet.spread_at_pick) : ""}
            </span>
          )}
          {isProp && bet.player_name && (
            <span className="font-mono text-xs text-secondary">
              {bet.player_name} {bet.stat_type} {bet.prop_direction === "OVER" ? "o" : "u"}{bet.prop_line}
            </span>
          )}
          {isProp && bet.projection != null && (
            <span className="text-[10px] text-muted-foreground">
              proj:{bet.projection.toFixed(1)}
            </span>
          )}
          {bet.cover_pct != null && (
            <span className="text-[10px] text-muted-foreground">
              {bet.cover_pct.toFixed(1)}%
            </span>
          )}
          {bet.actual_value != null && (
            <span className="text-[10px] font-mono text-foreground">
              actual:{bet.actual_value}
            </span>
          )}
        </div>

        {/* Row 3: Date + score */}
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] text-muted-foreground font-mono">
            {new Date(bet.created_at).toLocaleDateString()}
          </span>
          {bet.home_score != null && bet.away_score != null && (
            <span className="text-[10px] text-muted-foreground font-mono">
              {bet.away_score}-{bet.home_score}
            </span>
          )}
          {bet.clv != null && (
            <span className={`text-[10px] font-mono ${bet.clv > 0 ? "text-success" : "text-primary"}`}>
              CLV:{bet.clv > 0 ? "+" : ""}{bet.clv.toFixed(1)}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <span className={`text-[10px] font-heading px-1.5 py-0.5 border rounded-sm ${resultBadge(bet.result)}`}>
          {bet.result}
        </span>
        {bet.result === "PENDING" && (
          <button
            onClick={() => deleteBet.mutate(bet.id)}
            className="p-1 text-muted-foreground hover:text-primary transition-colors"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        )}
      </div>
    </div>
  );
}

export function MyBetsPage({ sport }: MyBetsPageProps) {
  const activeSport = sport ? toLowerSport(sport) : undefined;
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  const { data: combinedData, isLoading } = useBetsCombined(activeSport, statusFilter);
  const bets = combinedData?.bets ?? [];
  const dashboard = combinedData?.dashboard;
  const gradeBets = useGradeBets();
  const deleteBet = useDeleteBet();

  // Auto-grade PENDING bets on page load (once per mount)
  const hasAutoGraded = useRef(false);
  useEffect(() => {
    if (hasAutoGraded.current) return;
    if (!bets.length) return;
    const hasPending = bets.some((b) => b.result === "PENDING");
    if (hasPending) {
      hasAutoGraded.current = true;
      gradeBets.mutate(undefined, {
        onSuccess: (data) => {
          if (data && data.graded > 0) {
            toast.success(`Graded ${data.graded} bets: ${data.wins}W/${data.losses}L/${data.pushes}P`);
          }
        },
      });
    }
  }, [bets]);

  const statuses = ["ALL", "PENDING", "WIN", "LOSS", "PUSH"];
  const overall = dashboard?.overall;

  return (
    <div className="py-6 px-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-heading text-xl tracking-wider text-foreground">
          MY <span className="text-secondary">BETS</span>
        </h2>
        <button
          onClick={() =>
            gradeBets.mutate(undefined, {
              onSuccess: (data) => {
                if (data && data.graded > 0) {
                  toast.success(`Graded ${data.graded} bets: ${data.wins}W/${data.losses}L/${data.pushes}P`);
                } else {
                  toast.info("No bets to grade");
                }
              },
            })
          }
          disabled={gradeBets.isPending}
          className="px-4 py-2 text-xs font-heading tracking-wider bg-secondary/15 text-secondary border border-secondary/30 rounded-sm hover:bg-secondary/25 transition-colors disabled:opacity-50"
        >
          {gradeBets.isPending ? "GRADING..." : "GRADE ALL"}
        </button>
      </div>

      {/* Dashboard stats */}
      {overall && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">RECORD</p>
            <p className="font-mono text-xl text-foreground">
              {overall.wins}-{overall.losses}-{overall.pushes}
            </p>
          </div>
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">WIN RATE</p>
            <p className={`font-mono text-xl ${overall.win_rate >= 55 ? "text-success" : overall.win_rate >= 50 ? "text-foreground" : "text-primary"}`}>
              {overall.win_rate.toFixed(1)}%
            </p>
          </div>
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">ROI</p>
            <p className={`font-mono text-xl ${overall.roi >= 0 ? "text-success" : "text-primary"}`}>
              {overall.roi >= 0 ? "+" : ""}{overall.roi.toFixed(1)}%
            </p>
          </div>
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">TOTAL</p>
            <p className="font-mono text-xl text-foreground">{overall.total}</p>
          </div>
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">PENDING</p>
            <p className="font-mono text-xl text-warning">{overall.pending}</p>
          </div>
        </div>
      )}

      {/* Status filter */}
      <div className="flex items-center gap-1 mb-4">
        {statuses.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s === "ALL" ? undefined : s)}
            className={`px-3 py-1.5 text-xs font-heading tracking-wider rounded-sm transition-colors ${
              (s === "ALL" && !statusFilter) || statusFilter === s
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider animate-pulse">
            LOADING BETS...
          </p>
        </div>
      )}

      {bets.length > 0 && (
        <div className="card-surface rounded-sm overflow-hidden">
          {bets.map((bet) => (
            <BetLine key={bet.id} bet={bet} />
          ))}
        </div>
      )}

      {!isLoading && bets.length === 0 && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider">
            No bets found
          </p>
        </div>
      )}
    </div>
  );
}
