import { useDashboard } from "@/hooks/use-dashboard";
import { useBetsCombined } from "@/hooks/use-bets";
import { useAllGameCounts } from "@/hooks/use-games";
import { SystemStatusBar } from "./SystemStatusBar";
import { MetricGaugeRow } from "./MetricGaugeRow";
import { PnlChart } from "./PnlChart";
import { SportCommandCards } from "./SportCommandCards";
import { RecentMissionLog } from "./RecentMissionLog";
import { PerformanceRadar } from "./PerformanceRadar";
import { ScanlineOverlay } from "@/components/jarvis/ScanlineOverlay";
import type { Sport } from "@/lib/types";

interface CommandCenterProps {
  onSelectSport: (sport: Sport) => void;
}

export function CommandCenter({ onSelectSport }: CommandCenterProps) {
  const { data: dashboard, isLoading } = useDashboard();
  const { data: betsData } = useBetsCombined();
  const gameCounts = useAllGameCounts();
  const totalGames = Object.values(gameCounts).reduce((a, b) => a + b, 0);

  const overall = dashboard?.overall;
  const cumulativePnl = betsData?.dashboard?.cumulative_pnl;
  const monthlyBreakdown = dashboard?.monthly_breakdown;
  const clvAvg = dashboard?.clv ? (dashboard.clv as Record<string, unknown>).avg_clv as number | undefined : undefined;

  return (
    <div className="relative py-4 sm:py-6 px-3 sm:px-6 max-w-7xl mx-auto space-y-4">
      <ScanlineOverlay />

      {/* System Status */}
      <SystemStatusBar totalGames={totalGames} />

      {/* Metric Gauges */}
      <MetricGaugeRow overall={overall} drawdown={dashboard?.drawdown} streaks={dashboard?.streaks} isLoading={isLoading} />

      {/* Charts Row: P&L (8col) + Radar (4col) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="lg:col-span-8">
          <PnlChart data={cumulativePnl} monthly={monthlyBreakdown} isLoading={isLoading} />
        </div>
        <div className="lg:col-span-4">
          <PerformanceRadar overall={overall} variance={dashboard?.variance} streaks={dashboard?.streaks} clvAvg={clvAvg} isLoading={isLoading} />
        </div>
      </div>

      {/* Sport Command Cards */}
      <SportCommandCards gameCounts={gameCounts} onSelectSport={onSelectSport} />

      {/* Recent Mission Log */}
      <RecentMissionLog recent={dashboard?.recent} />
    </div>
  );
}
