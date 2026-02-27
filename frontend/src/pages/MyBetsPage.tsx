import { useState } from "react";
import { Trash2 } from "lucide-react";
import { useTrackedBets, useGradeBets, useDeleteBet, useBetsDashboard } from "@/hooks/use-bets";
import { toLowerSport, type Sport } from "@/lib/types";

interface MyBetsPageProps {
  sport: Sport | null;
}

export function MyBetsPage({ sport }: MyBetsPageProps) {
  const activeSport = sport ? toLowerSport(sport) : undefined;
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);

  const { data: betsData, isLoading } = useTrackedBets(activeSport, statusFilter);
  const { data: dashData } = useBetsDashboard(activeSport);
  const gradeBets = useGradeBets();
  const deleteBet = useDeleteBet();

  const statuses = ["ALL", "PENDING", "WIN", "LOSS", "PUSH"];
  const overall = dashData?.overall;

  return (
    <div className="py-6 px-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-heading text-xl tracking-wider text-foreground">
          MY <span className="text-secondary">BETS</span>
        </h2>
        <button
          onClick={() => gradeBets.mutate()}
          disabled={gradeBets.isPending}
          className="px-4 py-2 text-xs font-heading tracking-wider bg-secondary/15 text-secondary border border-secondary/30 rounded-sm hover:bg-secondary/25 transition-colors disabled:opacity-50"
        >
          {gradeBets.isPending ? "GRADING..." : "GRADE ALL"}
        </button>
      </div>

      {/* Dashboard stats */}
      {overall && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">TOTAL BETS</p>
            <p className="font-mono text-xl text-foreground">{overall.total}</p>
          </div>
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">PENDING</p>
            <p className="font-mono text-xl text-warning">{overall.pending}</p>
          </div>
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">ROI</p>
            <p className={`font-mono text-xl ${overall.roi >= 0 ? "text-success" : "text-primary"}`}>
              {overall.roi >= 0 ? "+" : ""}{overall.roi.toFixed(1)}%
            </p>
          </div>
          <div className="card-surface rounded-sm p-4">
            <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">RECORD</p>
            <p className="font-mono text-xl text-foreground">
              {overall.wins}-{overall.losses}-{overall.pushes}
            </p>
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

      {betsData?.bets && betsData.bets.length > 0 && (
        <div className="card-surface rounded-sm overflow-hidden">
          {betsData.bets.map((bet) => (
            <div
              key={bet.id}
              className="flex items-center justify-between px-4 py-3 border-b border-border/30 hover:bg-muted/20"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-heading text-muted-foreground uppercase">
                    {bet.sport}
                  </span>
                  <span className="font-mono text-xs text-foreground">{bet.team}</span>
                  <span className="text-[10px] text-muted-foreground">
                    {bet.type === "prop" ? `${bet.stat} ${bet.line}` : `${bet.line > 0 ? "+" : ""}${bet.line}`}
                  </span>
                </div>
                <span className="text-[10px] text-muted-foreground font-mono">
                  {new Date(bet.created_at).toLocaleDateString()}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span
                  className={`text-[10px] font-heading px-1.5 py-0.5 border rounded-sm ${
                    bet.status === "WIN"
                      ? "bg-success/15 text-success border-success/30"
                      : bet.status === "LOSS"
                      ? "bg-primary/15 text-primary border-primary/30"
                      : bet.status === "PUSH"
                      ? "bg-warning/15 text-warning border-warning/30"
                      : "bg-muted text-muted-foreground border-border"
                  }`}
                >
                  {bet.status}
                </span>

                {bet.status === "PENDING" && (
                  <button
                    onClick={() => deleteBet.mutate(bet.id)}
                    className="p-1 text-muted-foreground hover:text-primary transition-colors"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {betsData?.bets && betsData.bets.length === 0 && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider">
            No bets found
          </p>
        </div>
      )}
    </div>
  );
}
