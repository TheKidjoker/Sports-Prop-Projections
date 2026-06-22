import { memo } from "react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { ChartSkeleton } from "@/components/jarvis/ChartSkeleton";
import { CHART_COLORS, CHART_AXIS_STYLE, CHART_GRID_STYLE } from "@/lib/chart-theme";
import type { PeriodBreakdown } from "@/lib/types";

interface PnlChartProps {
  data?: { date: string; pnl: number }[];
  monthly?: PeriodBreakdown[];
  isLoading?: boolean;
}

export const PnlChart = memo(function PnlChart({ data, monthly, isLoading }: PnlChartProps) {
  if (isLoading) return <ChartSkeleton height={260} />;

  // Build chart data from cumulative_pnl or derive from monthly
  let chartData: { label: string; pnl: number }[] = [];
  if (data && data.length > 0) {
    chartData = data.map(d => ({ label: d.date, pnl: d.pnl }));
  } else if (monthly && monthly.length > 0) {
    let cum = 0;
    chartData = monthly.map(m => {
      cum += m.roi;
      return { label: m.period_label, pnl: parseFloat(cum.toFixed(1)) };
    });
  }

  if (chartData.length === 0) {
    return (
      <HudPanel title="CUMULATIVE P&L">
        <p className="text-muted-foreground text-xs text-center py-8">No data available</p>
      </HudPanel>
    );
  }

  return (
    <HudPanel title="CUMULATIVE P&L" status="online">
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <AreaChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLORS.crimson} stopOpacity={0.3} />
                <stop offset="100%" stopColor={CHART_COLORS.crimson} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid {...CHART_GRID_STYLE} />
            <XAxis dataKey="label" {...CHART_AXIS_STYLE} tick={{ fontSize: 9 }} />
            <YAxis {...CHART_AXIS_STYLE} tick={{ fontSize: 9 }} />
            <Tooltip
              contentStyle={{ background: CHART_COLORS.surface, border: `1px solid ${CHART_COLORS.grid}`, borderRadius: 2, fontSize: 11, fontFamily: "'JetBrains Mono', monospace" }}
              labelStyle={{ color: CHART_COLORS.foregroundMuted }}
            />
            <ReferenceLine y={0} stroke={CHART_COLORS.foregroundMuted} strokeDasharray="3 3" />
            <Area type="monotone" dataKey="pnl" stroke={CHART_COLORS.crimson} fill="url(#pnlGrad)" strokeWidth={2} style={{ filter: `drop-shadow(0 0 4px ${CHART_COLORS.crimsonMuted})` }} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </HudPanel>
  );
});
