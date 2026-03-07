import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle } from "lucide-react";
import { PickCard } from "./PickCard";
import { PickCardSkeleton } from "./PickCardSkeleton";
import { LogoLoader } from "@/components/ui/LogoLoader";
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

  // Prefetch props in background after scan completes
  useEffect(() => {
    if (!isScanning && picks.length > 0 && ["nba", "nhl", "cbb"].includes(lowerSport)) {
      queryClient.prefetchQuery({
        queryKey: ["top-props", lowerSport],
        queryFn: () => fetchTopProps(lowerSport),
        staleTime: 60_000,
      });
    }
  }, [isScanning, picks.length, lowerSport, queryClient]);

  // Sort all picks by confidence descending
  const sorted = [...picks].sort((a, b) => b.coverPct - a.coverPct);

  const topPicks = sorted.filter((p) => p.coverPct >= 68.5);
  const watchPicks = sorted.filter((p) => p.coverPct >= 55 && p.coverPct < 68.5);
  const otherGames = sorted.filter((p) => p.coverPct < 55);

  return (
    <div className="py-4 sm:py-6 px-3 sm:px-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-2 sm:gap-3 mb-4 sm:mb-6">
        <h2 className="font-heading text-lg sm:text-xl tracking-wider text-foreground">
          {sport} <span className="text-primary">SCAN RESULTS</span>
        </h2>
        <span className="font-mono text-[10px] sm:text-xs text-muted-foreground">
          {picks.length} games
        </span>
      </div>

      {pendingReview && !isAdmin && (
        <div className="mb-4 px-4 py-2 bg-warning/10 border border-warning/30 rounded-sm flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-warning" />
          <span className="text-xs text-warning font-heading tracking-wider">
            PICKS PENDING ADMIN REVIEW
          </span>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-2 bg-primary/10 border border-primary/30 rounded-sm flex items-center justify-between">
          <span className="text-xs text-primary font-mono">
            Scan error: {(error as Error).message}
          </span>
          <button
            type="button"
            onClick={() => scan()}
            className="text-xs text-primary font-heading tracking-wider hover:underline ml-4"
          >
            RETRY
          </button>
        </div>
      )}

      {isScanning ? (
        <div className="space-y-4">
          <LogoLoader text="SCANNING GAMES..." />
          {[1, 2, 3].map((i) => (
            <PickCardSkeleton key={i} />
          ))}
        </div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div key={sport} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {topPicks.length > 0 && (
              <div className="mb-8">
                <h3 className="font-heading text-xs tracking-[0.2em] text-primary mb-3">
                  TOP PICKS
                </h3>
                <div className="space-y-3">
                  {topPicks.map((pick, i) => (
                    <PickCard key={pick.id} pick={pick} index={i} isAdmin={isAdmin} onTrackBet={onTrackBet} />
                  ))}
                </div>
              </div>
            )}

            {watchPicks.length > 0 && (
              <div className="mb-8">
                <h3 className="font-heading text-xs tracking-[0.2em] text-secondary mb-3">
                  GAMES TO WATCH
                </h3>
                <div className="space-y-3">
                  {watchPicks.map((pick, i) => (
                    <PickCard key={pick.id} pick={pick} index={i + topPicks.length} isAdmin={isAdmin} onTrackBet={onTrackBet} />
                  ))}
                </div>
              </div>
            )}

            {otherGames.length > 0 && (
              <div>
                <h3 className="font-heading text-xs tracking-[0.2em] text-muted-foreground mb-3">
                  ALL OTHER GAMES
                </h3>
                <div className="space-y-3">
                  {otherGames.map((pick, i) => (
                    <PickCard
                      key={pick.id}
                      pick={pick}
                      index={i + topPicks.length + watchPicks.length}
                      isAdmin={isAdmin}
                      onTrackBet={onTrackBet}
                    />
                  ))}
                </div>
              </div>
            )}

            {picks.length === 0 && !isScanning && !error && (
              <div className="text-center py-10">
                <p className="text-muted-foreground text-sm font-heading tracking-wider">
                  No games found for {sport}
                </p>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}
