import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { PickCard } from "./PickCard";
import { PickCardSkeleton } from "./PickCardSkeleton";
import { LogoLoader } from "@/components/ui/LogoLoader";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { GaugeRing } from "@/components/jarvis/GaugeRing";
import { StatusIndicator } from "@/components/jarvis/StatusIndicator";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { CHART_COLORS } from "@/lib/chart-theme";
import { useScan } from "@/hooks/use-scan";
import { fetchTopProps } from "@/lib/api";
import { toLowerSport, type Sport } from "@/lib/types";
import type { BetSlipItem } from "@/components/bets/BetSlip";

interface ScanResultsProps {
  sport: Sport;
  isAdmin?: boolean;
  onTrackBet?: (bet: BetSlipItem) => void;
}

export function ScanResults({ sport, isAdmin, onTrackBet }: ScanResultsProps) {
  const lowerSport = toLowerSport(sport);
  const queryClient = useQueryClient();
  const { scan, isScanning, picks, pendingReview, error } = useScan(lowerSport);

  useEffect(() => {
    scan();
  }, [sport]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isScanning && picks.length > 0 && ["nba", "nhl", "cbb", "soccer"].includes(lowerSport)) {
      queryClient.prefetchQuery({
        queryKey: ["top-props", lowerSport],
        queryFn: () => fetchTopProps(lowerSport),
        staleTime: 60_000,
      });
    }
  }, [isScanning, picks.length, lowerSport, queryClient]);

  const sorted = [...picks].sort((a, b) => b.coverPct - a.coverPct);
  const topPicks = sorted.filter((p) => p.coverPct >= 65);
  const watchPicks = sorted.filter((p) => p.coverPct >= 55 && p.coverPct < 65);
  const otherGames = sorted.filter((p) => p.coverPct < 55);
  const avgConf = picks.length > 0 ? picks.reduce((s, p) => s + p.coverPct, 0) / picks.length : 0;

  return (
    <div className="py-4 sm:py-6 px-3 sm:px-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="font-heading text-lg sm:text-xl tracking-wider text-foreground">
            PICKS — <span className="text-primary">{sport}</span>
          </h2>
          <StatusIndicator status={isScanning ? "warning" : "online"} label={isScanning ? "SCANNING" : "COMPLETE"} />
        </div>
      </div>

      {/* Summary bar */}
      {!isScanning && picks.length > 0 && (
        <HudPanel className="mb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div>
                <span className="text-[13px] font-heading tracking-wider text-muted-foreground">TOTAL GAMES</span>
                <p className="font-mono text-xl text-foreground">{picks.length}</p>
              </div>
              <div>
                <span className="text-[13px] font-heading tracking-wider text-muted-foreground">TOP PICKS</span>
                <p className="font-mono text-xl text-primary">{topPicks.length}</p>
              </div>
              <div>
                <span className="text-[13px] font-heading tracking-wider text-muted-foreground">WATCH LIST</span>
                <p className="font-mono text-xl text-secondary">{watchPicks.length}</p>
              </div>
            </div>
            <GaugeRing value={avgConf} max={100} label="AVG CONFIDENCE" unit="%" size={64} color={avgConf >= 60 ? CHART_COLORS.green : CHART_COLORS.crimson} />
          </div>
        </HudPanel>
      )}

      {pendingReview && !isAdmin && (
        <div className="mb-4 px-4 py-2 hud-panel flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-warning" />
          <span className="text-xs text-warning font-heading tracking-wider">PICKS PENDING ADMIN REVIEW</span>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-2 hud-panel flex items-center justify-between">
          <span className="text-xs text-primary font-mono">Scan error: {(error as Error).message}</span>
          <button onClick={() => scan()} className="text-xs text-primary font-heading tracking-wider hover:underline ml-4">RETRY</button>
        </div>
      )}

      {isScanning ? (
        <div className="space-y-4">
          <LogoLoader text="SCANNING INTEL..." />
          {[1, 2, 3].map((i) => <PickCardSkeleton key={i} />)}
        </div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div key={sport} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {topPicks.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-8 h-[1px] bg-primary" />
                  <HexBadge label="TOP PICKS" color={CHART_COLORS.crimson} size="md" active />
                  <div className="flex-1 h-[1px] bg-border" />
                </div>
                <div className="space-y-3">
                  {topPicks.map((pick, i) => (
                    <PickCard key={pick.id} pick={pick} index={i} isAdmin={isAdmin} onTrackBet={onTrackBet} />
                  ))}
                </div>
              </div>
            )}

            {watchPicks.length > 0 && (
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-8 h-[1px] bg-secondary" />
                  <HexBadge label="WATCH LIST" color={CHART_COLORS.gold} size="md" active />
                  <div className="flex-1 h-[1px] bg-border" />
                </div>
                <div className="space-y-3">
                  {watchPicks.map((pick, i) => (
                    <PickCard key={pick.id} pick={pick} index={i + topPicks.length} isAdmin={isAdmin} onTrackBet={onTrackBet} />
                  ))}
                </div>
              </div>
            )}

            {otherGames.length > 0 && (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-8 h-[1px] bg-muted-foreground" />
                  <HexBadge label="ALL GAMES" color={CHART_COLORS.muted} size="md" />
                  <div className="flex-1 h-[1px] bg-border" />
                </div>
                <div className="space-y-3">
                  {otherGames.map((pick, i) => (
                    <PickCard key={pick.id} pick={pick} index={i + topPicks.length + watchPicks.length} isAdmin={isAdmin} onTrackBet={onTrackBet} />
                  ))}
                </div>
              </div>
            )}

            {picks.length === 0 && !isScanning && !error && (
              <div className="text-center py-10">
                <p className="text-muted-foreground text-sm font-heading tracking-wider">NO INTEL FOUND FOR {sport}</p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}
