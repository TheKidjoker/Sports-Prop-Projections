import { useState } from "react";
import { useDashboard, useGradePredictions } from "@/hooks/use-dashboard";
import { StatsCards } from "@/components/dashboard/StatsCards";
import { toLowerSport, type Sport } from "@/lib/types";

interface LedgerPageProps {
  sport: Sport | null;
}

export function LedgerPage({ sport }: LedgerPageProps) {
  const activeSport = sport ? toLowerSport(sport) : undefined;
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const { data, isLoading } = useDashboard(activeSport, startDate || undefined, endDate || undefined);
  const grade = useGradePredictions();

  const overall = data?.overall;

  return (
    <div className="py-6 px-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-heading text-xl tracking-wider text-foreground">
          THE <span className="text-primary">LEDGER</span>
        </h2>
        <button
          onClick={() => grade.mutate(activeSport)}
          disabled={grade.isPending}
          className="px-4 py-2 text-xs font-heading tracking-wider bg-primary/15 text-primary border border-primary/30 rounded-sm hover:bg-primary/25 transition-colors disabled:opacity-50"
        >
          {grade.isPending ? "GRADING..." : "GRADE PICKS"}
        </button>
      </div>

      {/* Date range filter */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <span className="text-[10px] font-heading tracking-wider text-muted-foreground">DATE RANGE:</span>
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="px-2 py-1 text-xs font-mono bg-background border border-border rounded-sm text-foreground"
        />
        <span className="text-muted-foreground text-xs">to</span>
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          className="px-2 py-1 text-xs font-mono bg-background border border-border rounded-sm text-foreground"
        />
        {(startDate || endDate) && (
          <button
            onClick={() => { setStartDate(""); setEndDate(""); }}
            className="px-2 py-1 text-[10px] font-heading text-muted-foreground hover:text-foreground transition-colors"
          >
            CLEAR
          </button>
        )}
      </div>

      {isLoading && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider animate-pulse">
            LOADING LEDGER...
          </p>
        </div>
      )}

      {overall && (
        <>
          <StatsCards
            total={overall.total}
            accuracy={overall.win_rate}
            pending={overall.pending}
            hits={overall.wins}
            misses={overall.losses}
            pushes={overall.pushes}
          />

          {grade.data && (
            <div className="mb-4 px-4 py-2 bg-success/10 border border-success/30 rounded-sm">
              <span className="text-xs text-success font-mono">
                Graded {grade.data.graded} picks
              </span>
            </div>
          )}

          {/* By Recommendation breakdown */}
          {data?.by_recommendation && data.by_recommendation.length > 0 && (
            <div className="mb-6">
              <h3 className="font-heading text-xs tracking-[0.2em] text-muted-foreground mb-3">
                BY RECOMMENDATION
              </h3>
              <div className="card-surface rounded-sm overflow-hidden">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-border bg-muted/30">
                      <th className="text-left px-4 py-2 font-heading tracking-wider text-muted-foreground">TIER</th>
                      <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">TOTAL</th>
                      <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">W</th>
                      <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">L</th>
                      <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">WIN%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_recommendation.map((row) => (
                      <tr key={String(row.recommendation)} className="border-b border-border/30 hover:bg-muted/20">
                        <td className="px-4 py-2 font-mono text-foreground">{String(row.recommendation)}</td>
                        <td className="text-right px-3 py-2 font-mono text-muted-foreground">{row.total}</td>
                        <td className="text-right px-3 py-2 font-mono text-success">{row.wins}</td>
                        <td className="text-right px-3 py-2 font-mono text-primary">{row.losses}</td>
                        <td className={`text-right px-3 py-2 font-mono ${row.win_rate >= 55 ? "text-success" : "text-foreground"}`}>
                          {row.win_rate.toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Recent predictions */}
          {data?.recent && data.recent.length > 0 && (
            <div>
              <h3 className="font-heading text-xs tracking-[0.2em] text-muted-foreground mb-3">
                RECENT PICKS
              </h3>
              <div className="card-surface rounded-sm overflow-hidden">
                {data.recent.map((pred) => (
                  <div
                    key={pred.event_id}
                    className="flex items-center justify-between px-4 py-2 border-b border-border/30 hover:bg-muted/20"
                  >
                    <div className="flex-1 min-w-0">
                      <span className="font-mono text-xs text-foreground">
                        {pred.away_team} @ {pred.home_team}
                      </span>
                      <span className="text-[10px] text-muted-foreground ml-2">
                        {pred.lean_team} — {pred.recommendation}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] font-heading px-1.5 py-0.5 border rounded-sm ${
                        pred.result === "HIT"
                          ? "bg-success/15 text-success border-success/30"
                          : pred.result === "MISS"
                          ? "bg-primary/15 text-primary border-primary/30"
                          : pred.result === "PUSH"
                          ? "bg-warning/15 text-warning border-warning/30"
                          : "bg-muted text-muted-foreground border-border"
                      }`}
                    >
                      {pred.result || "PENDING"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
