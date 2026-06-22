import { useEffect, useMemo } from "react";
import { RefreshCw } from "lucide-react";
import { useParlays } from "@/hooks/use-parlays";
import {
  buildCrossSportParlays,
  ParlayCard,
} from "@/components/picks/ParlayBuilder";
import { LogoLoader } from "@/components/ui/LogoLoader";
import type { BetSlipItem } from "@/components/bets/BetSlip";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { StatusIndicator } from "@/components/jarvis/StatusIndicator";
import { CHART_COLORS } from "@/lib/chart-theme";

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
    return <LogoLoader text="SCANNING ALL THEATRES..." />;
  }

  // Error state
  if (scanError) {
    return (
      <div className="py-6 px-3 sm:px-6 max-w-5xl mx-auto">
        <HudPanel title="STRIKE OPS ERROR" status="error">
          <span className="text-xs font-mono" style={{ color: CHART_COLORS.crimson }}>
            {scanError instanceof Error ? scanError.message : "Unknown error"}
          </span>
        </HudPanel>
      </div>
    );
  }

  return (
    <div className="py-6 px-3 sm:px-6 max-w-5xl mx-auto space-y-4">
      {/* ── Page Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="font-heading text-lg sm:text-xl tracking-widest text-foreground uppercase">
            Strike Operations{" "}
            <span style={{ color: CHART_COLORS.crimson }}>/ Cross-Sport Parlays</span>
          </h2>
        </div>

        <button
          onClick={() => triggerScan()}
          disabled={scanLoading}
          className="hud-btn px-3 py-1.5 text-[10px] font-heading tracking-widest uppercase flex items-center gap-1.5"
          style={{
            borderColor: `${CHART_COLORS.crimson}50`,
            color: CHART_COLORS.crimson,
            background: `${CHART_COLORS.crimson}10`,
          }}
        >
          <RefreshCw className="w-3 h-3" />
          RESCAN
        </button>
      </div>

      {/* ── Props loading status ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <HexBadge
            label={`${allPicks.length} PICKS`}
            color={CHART_COLORS.gold}
            size="md"
            active={allPicks.length > 0}
          />
          <HexBadge
            label={`${parlays.length} PARLAYS`}
            color={CHART_COLORS.green}
            size="md"
            active={parlays.length > 0}
          />
        </div>

        <div className="flex items-center gap-2">
          {propsLoading && (
            <StatusIndicator status="warning" label={`LOADING PROPS ${propsComplete}/${propsTotal}`} />
          )}
          {!propsLoading && propsComplete > 0 && (
            <StatusIndicator status="online" label="ALL PROPS LOADED" />
          )}
        </div>
      </div>

      {/* ── Parlays Grid ── */}
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
        <HudPanel title="NO STRIKE PACKAGES" status="offline">
          <p className="text-muted-foreground text-xs font-heading tracking-wider text-center py-8">
            {allPicks.length === 0
              ? "No actionable games across any theatre of operations"
              : "No parlay combinations meet confidence thresholds"}
          </p>
        </HudPanel>
      )}
    </div>
  );
}
