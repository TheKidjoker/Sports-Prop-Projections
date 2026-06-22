import { memo } from "react";
import { Radar, RadarChart as RechartsRadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer } from "recharts";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { ChartSkeleton } from "@/components/jarvis/ChartSkeleton";
import { CHART_COLORS } from "@/lib/chart-theme";
import type { DashboardOverall, VarianceMetrics, StreakMetrics } from "@/lib/types";

interface PerformanceRadarProps {
  overall?: DashboardOverall;
  variance?: VarianceMetrics;
  streaks?: StreakMetrics;
  clvAvg?: number;
  isLoading?: boolean;
}

export const PerformanceRadar = memo(function PerformanceRadar({ overall, variance, streaks, clvAvg, isLoading }: PerformanceRadarProps) {
  if (isLoading || !overall) return <ChartSkeleton height={260} />;

  const winRate = Math.min(overall.win_rate, 100);
  const roi = Math.min(Math.max(((overall.wins - overall.losses) / Math.max(overall.total - overall.pending, 1)) * 100 + 20, 0), 40) / 40 * 100;
  const clv = Math.min(Math.max((clvAvg ?? 0) + 5, 0), 10) / 10 * 100;
  const streak = Math.min((streaks?.max_win ?? 0) * 10, 100);
  const volume = Math.min(overall.total / 2, 100);
  const consistency = variance ? Math.max(100 - variance.std_dev * 10, 0) : 50;

  const data = [
    { axis: "Win Rate", value: winRate },
    { axis: "ROI", value: roi },
    { axis: "CLV", value: clv },
    { axis: "Streak", value: streak },
    { axis: "Volume", value: volume },
    { axis: "Consistency", value: consistency },
  ];

  return (
    <HudPanel title="PERFORMANCE RADAR">
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <RechartsRadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
            <PolarGrid stroke={CHART_COLORS.grid} />
            <PolarAngleAxis dataKey="axis" tick={{ fontSize: 9, fill: CHART_COLORS.foregroundMuted, fontFamily: "'Oswald', sans-serif" }} />
            <Radar dataKey="value" stroke={CHART_COLORS.crimson} fill={CHART_COLORS.crimsonMuted} fillOpacity={0.4} strokeWidth={2} />
          </RechartsRadarChart>
        </ResponsiveContainer>
      </div>
    </HudPanel>
  );
});
