import { useState } from "react";
import { useDashboard, useGradePredictions } from "@/hooks/use-dashboard";
import { toLowerSport, type Sport, type DashboardOverall, type PeriodBreakdown } from "@/lib/types";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { GaugeRing } from "@/components/jarvis/GaugeRing";
import { StatusIndicator } from "@/components/jarvis/StatusIndicator";
import { GaugeSkeleton } from "@/components/jarvis/GaugeSkeleton";
import { TableRowSkeleton } from "@/components/jarvis/TableRowSkeleton";
import { DataStream } from "@/components/jarvis/DataStream";
import { CHART_COLORS, CHART_AXIS_STYLE, CHART_GRID_STYLE } from "@/lib/chart-theme";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";

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
  const monthlyData = data?.monthly_breakdown ?? [];

  /* Build cumulative P&L data from monthly breakdown */
  const cumulativePnl = monthlyData.reduce<{ period: string; pnl: number }[]>((acc, row) => {
    const prev = acc.length > 0 ? acc[acc.length - 1].pnl : 0;
    // Approximate P&L: wins minus losses as units
    const pnl = prev + row.roi;
    acc.push({ period: row.period_label, pnl });
    return acc;
  }, []);

  return (
    <div className="py-6 px-3 sm:px-6 max-w-5xl mx-auto space-y-4">
      {/* ── Page Header ── */}
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg sm:text-xl tracking-widest text-foreground uppercase">
          Ledger{" "}
          <span style={{ color: CHART_COLORS.crimson }}>/ Performance Analytics</span>
        </h2>
        <button
          onClick={() => grade.mutate(activeSport)}
          disabled={grade.isPending}
          className="hud-btn px-4 py-1.5 text-[13px] font-heading tracking-widest uppercase"
          style={{
            borderColor: `${CHART_COLORS.crimson}50`,
            color: CHART_COLORS.crimson,
            background: `${CHART_COLORS.crimson}10`,
          }}
        >
          {grade.isPending ? "GRADING..." : "GRADE PICKS"}
        </button>
      </div>

      {/* ── Date Range Filter ── */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[12px] font-heading tracking-widest text-muted-foreground uppercase">Date Range:</span>
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="px-2 py-1 text-xs font-mono bg-transparent border border-white/10 text-foreground focus:border-white/20 outline-none"
          style={{ clipPath: "polygon(4% 0%, 96% 0%, 100% 50%, 96% 100%, 4% 100%, 0% 50%)" }}
        />
        <span className="text-muted-foreground text-[13px] font-heading tracking-widest">TO</span>
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          className="px-2 py-1 text-xs font-mono bg-transparent border border-white/10 text-foreground focus:border-white/20 outline-none"
          style={{ clipPath: "polygon(4% 0%, 96% 0%, 100% 50%, 96% 100%, 4% 100%, 0% 50%)" }}
        />
        {(startDate || endDate) && (
          <button
            onClick={() => { setStartDate(""); setEndDate(""); }}
            className="px-2 py-1 text-[12px] font-heading tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors"
          >
            CLEAR
          </button>
        )}
      </div>

      {/* ── Loading ── */}
      {isLoading && (
        <div className="flex items-center justify-center gap-6 py-8">
          <GaugeSkeleton />
          <GaugeSkeleton />
          <GaugeSkeleton />
          <GaugeSkeleton />
        </div>
      )}

      {overall && (
        <>
          {/* ── Gauge Row ── */}
          <HudPanel title="OPERATIONAL METRICS" status="online">
            <div className="flex items-center justify-around flex-wrap gap-4 py-2">
              <GaugeRing
                value={overall.win_rate}
                max={100}
                label="WIN RATE"
                unit="%"
                size={90}
                color={overall.win_rate >= 55 ? CHART_COLORS.green : overall.win_rate >= 50 ? CHART_COLORS.gold : CHART_COLORS.crimson}
              />
              <GaugeRing
                value={overall.total > 0 ? (overall.wins / overall.total) * 100 : 0}
                max={100}
                label={`RECORD ${overall.wins}-${overall.losses}-${overall.pushes}`}
                unit="%"
                size={90}
                color={CHART_COLORS.gold}
              />
              <GaugeRing
                value={overall.total}
                max={Math.max(overall.total, 100)}
                label="TOTAL OPS"
                unit=""
                size={90}
                color={CHART_COLORS.crimson}
              />
              <GaugeRing
                value={overall.pending}
                max={Math.max(overall.pending, 20)}
                label="PENDING"
                unit=""
                size={90}
                color={CHART_COLORS.gold}
              />
            </div>
          </HudPanel>

          {/* ── Grade result ── */}
          {grade.data && (
            <HudPanel status="online">
              <div className="flex items-center gap-2">
                <StatusIndicator status="online" label={`Graded ${grade.data.graded} picks`} />
              </div>
            </HudPanel>
          )}

          {/* ── Cumulative P&L Chart ── */}
          {cumulativePnl.length > 1 && (
            <HudPanel title="CUMULATIVE P&L TRAJECTORY" status="online">
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={cumulativePnl} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={CHART_COLORS.green} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={CHART_COLORS.green} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid {...CHART_GRID_STYLE} />
                    <XAxis dataKey="period" tick={CHART_AXIS_STYLE} tickLine={false} axisLine={false} />
                    <YAxis tick={CHART_AXIS_STYLE} tickLine={false} axisLine={false} />
                    <ReferenceLine y={0} stroke={CHART_COLORS.foregroundMuted} strokeDasharray="3 3" />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: CHART_COLORS.surface,
                        border: `1px solid ${CHART_COLORS.grid}`,
                        borderRadius: 0,
                        fontSize: 11,
                        fontFamily: "'JetBrains Mono', monospace",
                      }}
                      labelStyle={{ color: CHART_COLORS.foreground }}
                      itemStyle={{ color: CHART_COLORS.green }}
                    />
                    <Area
                      type="monotone"
                      dataKey="pnl"
                      stroke={CHART_COLORS.green}
                      fill="url(#pnlGrad)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </HudPanel>
          )}

          {/* ── By Recommendation ── */}
          {data?.by_recommendation && data.by_recommendation.length > 0 && (
            <HudPanel title="BY RECOMMENDATION TIER" status="online">
              {/* Angular table header */}
              <div className="flex items-center gap-3 px-2 py-1.5 border-b border-white/[0.06] text-[12px] font-heading tracking-widest text-muted-foreground uppercase">
                <div className="flex-1">TIER</div>
                <span className="w-12 text-right">TOTAL</span>
                <span className="w-10 text-right">W</span>
                <span className="w-10 text-right">L</span>
                <span className="w-14 text-right">WIN%</span>
              </div>
              {data.by_recommendation.map((row) => (
                <div
                  key={String(row.recommendation)}
                  className="flex items-center gap-3 px-2 py-2 border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
                >
                  <div className="flex-1 font-mono text-xs text-foreground">{String(row.recommendation)}</div>
                  <span className="w-12 text-right font-mono text-xs text-muted-foreground">{row.total}</span>
                  <span className="w-10 text-right font-mono text-xs" style={{ color: CHART_COLORS.green }}>{row.wins}</span>
                  <span className="w-10 text-right font-mono text-xs" style={{ color: CHART_COLORS.crimson }}>{row.losses}</span>
                  <span
                    className="w-14 text-right font-mono text-xs"
                    style={{ color: row.win_rate >= 55 ? CHART_COLORS.green : CHART_COLORS.foreground }}
                  >
                    {row.win_rate.toFixed(1)}%
                  </span>
                </div>
              ))}
            </HudPanel>
          )}

          {/* ── Recent Picks as DataStream ── */}
          {data?.recent && data.recent.length > 0 && (
            <HudPanel title="RECENT ACTIVITY" status="online">
              <DataStream
                className="max-h-64"
                items={data.recent.map((pred) => ({
                  id: pred.event_id,
                  label: `${pred.away_team} @ ${pred.home_team} — ${pred.lean_team} (${pred.recommendation})`,
                  detail: pred.result || "PENDING",
                  status: pred.result === "HIT" ? "success" : pred.result === "MISS" ? "error" : "pending",
                }))}
              />
            </HudPanel>
          )}
        </>
      )}
    </div>
  );
}
