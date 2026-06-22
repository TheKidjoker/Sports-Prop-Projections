import { GaugeRing } from "@/components/jarvis/GaugeRing";
import { GaugeSkeleton } from "@/components/jarvis/GaugeSkeleton";
import { CHART_COLORS } from "@/lib/chart-theme";
import type { DashboardOverall, DrawdownMetrics, StreakMetrics } from "@/lib/types";

interface MetricGaugeRowProps {
  overall?: DashboardOverall;
  drawdown?: DrawdownMetrics;
  streaks?: StreakMetrics;
  isLoading?: boolean;
}

export function MetricGaugeRow({ overall, drawdown, streaks, isLoading }: MetricGaugeRowProps) {
  if (isLoading || !overall) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 justify-items-center">
        {[1,2,3,4,5].map(i => <GaugeSkeleton key={i} />)}
      </div>
    );
  }

  const winRate = overall.win_rate;
  const roi = (overall.wins - overall.losses) / Math.max(overall.total - overall.pending, 1) * 100;
  const streakVal = streaks?.current?.count ?? 0;
  const streakColor = streaks?.current?.type === "W" ? CHART_COLORS.green : CHART_COLORS.crimson;
  const ddVal = drawdown?.current_drawdown ?? 0;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-4 justify-items-center">
      <GaugeRing value={winRate} max={100} label="WIN RATE" unit="%" size={80} color={winRate >= 55 ? CHART_COLORS.green : CHART_COLORS.crimson} />
      <GaugeRing value={roi} max={50} label="ROI" unit="%" size={80} color={roi >= 0 ? CHART_COLORS.green : CHART_COLORS.crimson} />
      <div className="flex flex-col items-center gap-1">
        <span className="font-mono text-xl text-foreground">{overall.wins}-{overall.losses}-{overall.pushes}</span>
        <span className="font-heading text-[9px] tracking-wider text-muted-foreground">RECORD</span>
      </div>
      <GaugeRing value={streakVal} max={20} label={`${streaks?.current?.type ?? "W"} STREAK`} unit="" size={80} color={streakColor} />
      <GaugeRing value={Math.abs(ddVal)} max={30} label="DRAWDOWN" unit="%" size={80} color={ddVal > 15 ? CHART_COLORS.crimson : CHART_COLORS.gold} />
    </div>
  );
}
