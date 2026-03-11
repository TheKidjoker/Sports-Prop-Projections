import { useEffect, useMemo } from "react";
import { useParlays } from "@/hooks/use-parlays";
import {
  buildCrossSportParlays,
  ParlayCard,
} from "@/components/picks/ParlayBuilder";
import { LogoLoader } from "@/components/ui/LogoLoader";
import type { BetSlipItem } from "@/components/bets/BetSlip";

interface ParlayPageProps {
  onTrackBet?: (bet: BetSlipItem) => void;
}

export function ParlayPage({ onTrackBet }: ParlayPageProps) {
  const {
    triggerScan,
    scanLoading,
    scanError,
    allPicks,
    allProps,
    propsLoading,
    propsComplete,
    propsTotal,
  } = useParlays();

  // Auto-trigger scan on mount
  useEffect(() => {
    triggerScan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Build parlays from picks + props (rebuilds as props arrive)
  const parlays = useMemo(
    () => buildCrossSportParlays(allPicks, allProps),
    [allPicks, allProps]
  );

  const handleTrackAll = (items: BetSlipItem[]) => {
    if (!onTrackBet) return;
    for (const item of items) {
      onTrackBet(item);
    }
  };

  // Loading state: scan still running
  if (scanLoading) {
    return <LogoLoader text="SCANNING ALL SPORTS..." />;
  }

  // Error state
  if (scanError) {
    return (
      <div className="py-6 px-6 max-w-5xl mx-auto">
        <div className="mb-4 px-4 py-2 bg-primary/10 border border-primary/30 rounded-sm">
          <span className="text-xs text-primary font-mono">
            Error: {scanError instanceof Error ? scanError.message : "Unknown error"}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="py-6 px-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-heading text-xl tracking-wider text-foreground">
          CROSS-SPORT <span className="text-secondary">PARLAYS</span>
        </h2>

        {/* Props loading indicator */}
        {propsLoading && (
          <span className="text-[10px] font-heading tracking-wider text-muted-foreground animate-pulse">
            LOADING PLAYER PROPS... {propsComplete}/{propsTotal} SPORTS
          </span>
        )}

        {!propsLoading && propsComplete > 0 && (
          <span className="text-[10px] font-heading tracking-wider text-success">
            ALL PROPS LOADED
          </span>
        )}
      </div>

      {/* Parlays grid */}
      {parlays.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {parlays.map((parlay) => (
            <ParlayCard
              key={parlay.name}
              parlay={parlay}
              onTrackAll={onTrackBet ? handleTrackAll : undefined}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider">
            {allPicks.length === 0
              ? "No games found across any sport"
              : "No parlays meet confidence thresholds"}
          </p>
        </div>
      )}
    </div>
  );
}
