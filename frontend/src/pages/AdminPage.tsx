import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { usePendingPicks, useApprovePick, useRejectPick, useApproveAll } from "@/hooks/use-picks";
import { fetchModelHealth } from "@/lib/api";
import { toLowerSport, type Sport, type SportLower } from "@/lib/types";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { GaugeRing } from "@/components/jarvis/GaugeRing";
import { StatusIndicator } from "@/components/jarvis/StatusIndicator";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { GaugeSkeleton } from "@/components/jarvis/GaugeSkeleton";
import { CHART_COLORS } from "@/lib/chart-theme";

interface AdminPageProps {
  sport: Sport | null;
}

/* ── health status color helper ── */
function healthStatus(accuracy?: number): "online" | "warning" | "error" {
  if (accuracy == null) return "error";
  if (accuracy >= 55) return "online";
  if (accuracy >= 50) return "warning";
  return "error";
}

function healthColor(accuracy?: number): string {
  if (accuracy == null) return CHART_COLORS.muted;
  if (accuracy >= 55) return CHART_COLORS.green;
  if (accuracy >= 50) return CHART_COLORS.gold;
  return CHART_COLORS.crimson;
}

/* ── recommendation badge color ── */
function recColor(rec: string): string {
  if (rec === "STRONG PLAY" || rec === "STRONG") return CHART_COLORS.crimson;
  if (rec === "CONFIDENT") return CHART_COLORS.gold;
  return CHART_COLORS.muted;
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
    <div className="py-6 px-3 sm:px-6 max-w-5xl mx-auto space-y-4">
      {/* ── Page Header ── */}
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg sm:text-xl tracking-widest text-foreground uppercase">
          System Administration
        </h2>
        <button
          onClick={() => approveAll.mutate(activeSport)}
          disabled={approveAll.isPending}
          className="hud-btn px-4 py-1.5 text-[10px] font-heading tracking-widest uppercase"
          style={{
            borderColor: `${CHART_COLORS.green}50`,
            color: CHART_COLORS.green,
            background: `${CHART_COLORS.green}10`,
          }}
        >
          {approveAll.isPending ? "APPROVING..." : "APPROVE ALL"}
        </button>
      </div>

      {/* ── Model Health Grid ── */}
      {healthData?.sports && (
        <HudPanel title="MODEL HEALTH MATRIX" status="online">
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
            {Object.entries(healthData.sports).map(([s, info]) => {
              const oos = info.out_of_sample;
              const status = healthStatus(oos?.accuracy);

              return (
                <div
                  key={s}
                  className="flex flex-col items-center gap-2 p-3 border border-white/[0.06] bg-white/[0.01] hover:bg-white/[0.02] transition-colors"
                >
                  <div className="flex items-center gap-2 w-full">
                    <StatusIndicator status={status} />
                    <span className="font-heading text-xs tracking-widest text-foreground uppercase">{s}</span>
                  </div>

                  {oos ? (
                    <>
                      <GaugeRing
                        value={oos.accuracy}
                        max={100}
                        label="ACCURACY"
                        unit="%"
                        size={70}
                        color={healthColor(oos.accuracy)}
                      />
                      <div className="text-center">
                        <span
                          className="font-mono text-[10px] block"
                          style={{ color: oos.roi >= 0 ? CHART_COLORS.green : CHART_COLORS.crimson }}
                        >
                          ROI: {oos.roi >= 0 ? "+" : ""}{oos.roi.toFixed(1)}%
                        </span>
                      </div>
                    </>
                  ) : (
                    <div className="py-4">
                      <GaugeSkeleton size={70} />
                      <p className="font-mono text-[9px] text-muted-foreground mt-2 text-center">NO OOS DATA</p>
                    </div>
                  )}

                  {info.overfit_gap != null && (
                    <span
                      className="font-mono text-[9px]"
                      style={{ color: info.overfit_gap > 10 ? CHART_COLORS.crimson : CHART_COLORS.muted }}
                    >
                      GAP: {info.overfit_gap.toFixed(1)}%
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </HudPanel>
      )}

      {/* ── Pending Picks ── */}
      <HudPanel
        title={`PENDING MISSIONS / ${activeSport.toUpperCase()}`}
        status={isLoading ? "warning" : picksData?.picks?.length ? "online" : "offline"}
        headerRight={
          <span className="font-mono text-[10px] text-muted-foreground">
            {picksData?.picks?.length ?? 0} pending
          </span>
        }
      >
        {isLoading && (
          <div className="text-center py-8">
            <p className="text-muted-foreground text-[10px] font-heading tracking-widest animate-pulse uppercase">
              Loading pending picks...
            </p>
          </div>
        )}

        {picksData?.picks && picksData.picks.length > 0 && (
          <div className="space-y-0">
            {picksData.picks.map((pick) => (
              <div
                key={pick.event_id}
                className="flex items-center justify-between px-3 py-3 border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-heading text-sm tracking-wider text-foreground">
                      {pick.away_team} @ {pick.home_team}
                    </span>
                    <HexBadge
                      label={pick.recommendation}
                      color={recColor(pick.recommendation)}
                      size="sm"
                      active
                    />
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-xs text-muted-foreground font-mono">
                      Lean: {pick.lean_team}
                    </span>
                    <span className="font-mono text-xs text-foreground tabular-nums">
                      {pick.cover_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>

                {/* Angular approve / reject buttons */}
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => approve.mutate({ eventId: pick.event_id, sport: activeSport })}
                    disabled={approve.isPending}
                    className="px-3 py-1 text-[9px] font-heading tracking-widest uppercase border transition-all hover:scale-105"
                    style={{
                      borderColor: `${CHART_COLORS.green}50`,
                      color: CHART_COLORS.green,
                      background: `${CHART_COLORS.green}10`,
                      clipPath: "polygon(8% 0%, 92% 0%, 100% 50%, 92% 100%, 8% 100%, 0% 50%)",
                    }}
                  >
                    APPROVE
                  </button>
                  <button
                    onClick={() => reject.mutate({ eventId: pick.event_id, sport: activeSport })}
                    disabled={reject.isPending}
                    className="px-3 py-1 text-[9px] font-heading tracking-widest uppercase border transition-all hover:scale-105"
                    style={{
                      borderColor: `${CHART_COLORS.crimson}50`,
                      color: CHART_COLORS.crimson,
                      background: `${CHART_COLORS.crimson}10`,
                      clipPath: "polygon(8% 0%, 92% 0%, 100% 50%, 92% 100%, 8% 100%, 0% 50%)",
                    }}
                  >
                    REJECT
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {picksData?.picks && picksData.picks.length === 0 && (
          <div className="text-center py-8">
            <p className="text-muted-foreground text-xs font-heading tracking-widest">
              No pending missions for {activeSport.toUpperCase()} theatre
            </p>
          </div>
        )}
      </HudPanel>
    </div>
  );
}
