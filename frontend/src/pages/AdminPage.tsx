import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePendingPicks, useApprovePick, useRejectPick, useApproveAll } from "@/hooks/use-picks";
import { fetchModelHealth } from "@/lib/api";
import { toLowerSport, type Sport, type SportLower } from "@/lib/types";

interface AdminPageProps {
  sport: Sport | null;
}

export function AdminPage({ sport }: AdminPageProps) {
  const activeSport: SportLower = sport ? toLowerSport(sport) : "nba";
  const { data: picksData, isLoading } = usePendingPicks(activeSport);
  const approve = useApprovePick();
  const reject = useRejectPick();
  const approveAll = useApproveAll();
  const { data: healthData } = useQuery({
    queryKey: ["model-health"],
    queryFn: fetchModelHealth,
  });

  return (
    <div className="py-6 px-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-heading text-xl tracking-wider text-foreground">
          <span className="text-secondary">ADMIN</span> PANEL
        </h2>
        <button
          onClick={() => approveAll.mutate(activeSport)}
          disabled={approveAll.isPending}
          className="px-4 py-2 text-xs font-heading tracking-wider bg-success/15 text-success border border-success/30 rounded-sm hover:bg-success/25 transition-colors disabled:opacity-50"
        >
          {approveAll.isPending ? "APPROVING..." : "APPROVE ALL"}
        </button>
      </div>

      {/* Model Health */}
      {healthData?.sports && (
        <div className="mb-8">
          <h3 className="font-heading text-xs tracking-[0.2em] text-muted-foreground mb-3">
            MODEL HEALTH
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {Object.entries(healthData.sports).map(([s, info]) => {
              const oos = info.out_of_sample;
              return (
                <div key={s} className="card-surface rounded-sm p-3">
                  <p className="font-heading text-sm tracking-wider text-foreground mb-1">
                    {s.toUpperCase()}
                  </p>
                  {oos ? (
                    <>
                      <p className={`font-mono text-lg ${oos.accuracy >= 55 ? "text-success" : "text-foreground"}`}>
                        {oos.accuracy.toFixed(1)}%
                      </p>
                      <p className={`font-mono text-[10px] ${oos.roi >= 0 ? "text-success" : "text-primary"}`}>
                        ROI: {oos.roi >= 0 ? "+" : ""}{oos.roi.toFixed(1)}%
                      </p>
                    </>
                  ) : (
                    <p className="font-mono text-xs text-muted-foreground">No OOS data</p>
                  )}
                  {info.overfit_gap != null && (
                    <p className={`font-mono text-[10px] ${info.overfit_gap > 10 ? "text-primary" : "text-muted-foreground"}`}>
                      Gap: {info.overfit_gap.toFixed(1)}%
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Pending Picks */}
      <h3 className="font-heading text-xs tracking-[0.2em] text-muted-foreground mb-3">
        PENDING PICKS — {activeSport.toUpperCase()}
      </h3>

      {isLoading && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider animate-pulse">
            LOADING PICKS...
          </p>
        </div>
      )}

      {picksData?.picks && picksData.picks.length > 0 && (
        <div className="card-surface rounded-sm overflow-hidden">
          {picksData.picks.map((pick) => (
            <div
              key={pick.event_id}
              className="flex items-center justify-between px-4 py-3 border-b border-border/30 hover:bg-muted/20"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-heading text-sm tracking-wider text-foreground">
                    {pick.away_team} @ {pick.home_team}
                  </span>
                  <span
                    className={`text-[10px] font-heading px-1.5 py-0.5 border rounded-sm ${
                      pick.recommendation === "STRONG PLAY" || pick.recommendation === "STRONG"
                        ? "bg-primary/15 text-primary border-primary/30"
                        : pick.recommendation === "CONFIDENT"
                        ? "bg-secondary/15 text-secondary border-secondary/30"
                        : "bg-muted text-muted-foreground border-border"
                    }`}
                  >
                    {pick.recommendation}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    Lean: {pick.lean_team}
                  </span>
                  <span className="font-mono text-xs text-foreground">
                    {pick.cover_pct.toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1">
                <button
                  onClick={() => approve.mutate({ eventId: pick.event_id, sport: activeSport })}
                  disabled={approve.isPending}
                  className="px-2 py-1 text-[10px] font-heading bg-success/15 text-success border border-success/30 rounded-sm hover:bg-success/25 transition-colors"
                >
                  APPROVE
                </button>
                <button
                  onClick={() => reject.mutate({ eventId: pick.event_id, sport: activeSport })}
                  disabled={reject.isPending}
                  className="px-2 py-1 text-[10px] font-heading bg-primary/15 text-primary border border-primary/30 rounded-sm hover:bg-primary/25 transition-colors"
                >
                  REJECT
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {picksData?.picks && picksData.picks.length === 0 && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider">
            No pending picks for {activeSport.toUpperCase()}
          </p>
        </div>
      )}
    </div>
  );
}
