import { useState, useMemo } from "react";
import { useTopProps } from "@/hooks/use-props";
import { PropRow } from "@/components/picks/PropRow";
import { LogoLoader } from "@/components/ui/LogoLoader";
import { toLowerSport, type Sport, type PropSignal } from "@/lib/types";
import type { BetSlipItem } from "@/components/bets/BetSlip";

interface PropsPageProps {
  sport: Sport | null;
  onTrackBet?: (bet: BetSlipItem) => void;
}

export function PropsPage({ sport, onTrackBet }: PropsPageProps) {
  const [loadAll, setLoadAll] = useState(false);
  const activeSport = sport ? toLowerSport(sport) : "nba";
  const { data, isLoading, error } = useTopProps(activeSport, loadAll);

  const propsAvailable = activeSport === "nba" || activeSport === "nhl";

  const sortedProps = useMemo(
    () => data?.props ? [...data.props].sort((a, b) => b.confidence - a.confidence) : [],
    [data?.props]
  );

  const handleTrackProp = (prop: PropSignal) => {
    if (!onTrackBet) return;
    const direction = prop.edge > 0 ? "OVER" : "UNDER";
    const dirLabel = direction === "OVER" ? "o" : "u";
    const home_team = prop.is_home ? prop.team : prop.opponent;
    const away_team = prop.is_home ? prop.opponent : prop.team;
    onTrackBet({
      event_id: prop.event_id,
      sport: activeSport,
      type: "prop",
      team: prop.team,
      stat: prop.stat_type,
      line: prop.line,
      label: `${prop.player_name} ${prop.stat_type} ${dirLabel}${prop.line}`,
      home_team,
      away_team,
      player_name: prop.player_name,
      direction,
      projection: prop.projection,
      edge: prop.edge,
      confidence: prop.confidence,
      signal: prop.signal,
    });
  };

  return (
    <div className="py-6 px-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h2 className="font-heading text-xl tracking-wider text-foreground">
            PLAYER <span className="text-secondary">PROPS</span>
          </h2>
          <span className="text-[9px] font-heading px-1.5 py-0.5 border rounded-sm bg-success/15 text-success border-success/30">
            VALIDATED
          </span>
        </div>
        {propsAvailable && (
          <button
            onClick={() => setLoadAll(true)}
            disabled={isLoading}
            className="px-4 py-2 text-xs font-heading tracking-wider bg-secondary/15 text-secondary border border-secondary/30 rounded-sm hover:bg-secondary/25 transition-colors disabled:opacity-50"
          >
            {isLoading ? "LOADING..." : "LOAD TOP PROPS"}
          </button>
        )}
      </div>

      {!propsAvailable && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider">
            Props are available for NBA and NHL only
          </p>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-2 bg-primary/10 border border-primary/30 rounded-sm">
          <span className="text-xs text-primary font-mono">
            Error: {(error as Error).message}
          </span>
        </div>
      )}

      {isLoading && loadAll && (
        <LogoLoader text="LOADING PROPS..." />
      )}

      {sortedProps.length > 0 && (
        <div className="card-surface rounded-sm overflow-hidden">
          {/* Header */}
          <div className="flex items-center gap-3 px-4 py-2 border-b border-border bg-muted/30 text-[10px] font-heading tracking-wider text-muted-foreground">
            <div className="flex-1">PLAYER</div>
            <span className="w-12 text-center">STAT</span>
            <span className="w-10 text-right">LINE</span>
            <span className="w-12 text-right">PROJ</span>
            <span className="w-14 text-right">EDGE</span>
            <span className="w-14 text-center">SIGNAL</span>
            <span className="w-8 text-right">CONF</span>
            <span className="w-6" />
          </div>
          {sortedProps.map((prop, i) => (
            <PropRow
              key={`${prop.player_name}-${prop.stat_type}-${i}`}
              prop={prop}
              onTrack={onTrackBet ? handleTrackProp : undefined}
            />
          ))}
        </div>
      )}

      {loadAll && !isLoading && sortedProps.length === 0 && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider">
            No props available
          </p>
        </div>
      )}

      {!loadAll && propsAvailable && (
        <div className="text-center py-10">
          <p className="text-muted-foreground text-sm font-heading tracking-wider">
            Click "LOAD TOP PROPS" to fetch player projections
          </p>
        </div>
      )}
    </div>
  );
}
