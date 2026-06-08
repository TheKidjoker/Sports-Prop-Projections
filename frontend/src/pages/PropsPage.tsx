import { useState, useMemo } from "react";
import { useTopProps } from "@/hooks/use-props";
import { PropRow } from "@/components/picks/PropRow";
import { LogoLoader } from "@/components/ui/LogoLoader";
import { toLowerSport, type Sport, type PropSignal } from "@/lib/types";
import type { BetSlipItem } from "@/components/bets/BetSlip";

const PROPS_PER_PAGE = 25;

interface PropsPageProps {
  sport: Sport | null;
  onTrackBet?: (bet: BetSlipItem) => void;
}

export function PropsPage({ sport, onTrackBet }: PropsPageProps) {
  const [loadAll, setLoadAll] = useState(false);
  const [page, setPage] = useState(0);
  const activeSport = sport ? toLowerSport(sport) : "nba";
  const { data, isLoading, error, refetch } = useTopProps(activeSport, loadAll);

  const propsAvailable = activeSport === "nba" || activeSport === "nhl" || activeSport === "cbb" || activeSport === "mlb";

  const sortedProps = useMemo(
    () => data?.props ? [...data.props].sort((a, b) => b.confidence - a.confidence) : [],
    [data?.props]
  );

  const totalPages = Math.ceil(sortedProps.length / PROPS_PER_PAGE);
  const pagedProps = sortedProps.slice(page * PROPS_PER_PAGE, (page + 1) * PROPS_PER_PAGE);

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
    <div className="py-6 px-3 sm:px-6 max-w-5xl mx-auto">
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
            onClick={() => { setLoadAll(true); setPage(0); }}
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
            Props are available for NBA, NHL, CBB, and MLB
          </p>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-2 bg-primary/10 border border-primary/30 rounded-sm flex items-center justify-between">
          <span className="text-xs text-primary font-mono">
            Error: {(error as Error).message}
          </span>
          <button
            onClick={() => refetch()}
            className="text-xs text-primary font-heading tracking-wider hover:underline ml-4"
          >
            RETRY
          </button>
        </div>
      )}

      {isLoading && loadAll && (
        <LogoLoader text="LOADING PROPS..." />
      )}

      {/* Desktop table view */}
      {pagedProps.length > 0 && (
        <div className="hidden sm:block card-surface rounded-sm overflow-hidden">
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
          {pagedProps.map((prop, i) => (
            <PropRow
              key={`${prop.player_name}-${prop.stat_type}-${page}-${i}`}
              prop={prop}
              onTrack={onTrackBet ? handleTrackProp : undefined}
            />
          ))}
        </div>
      )}

      {/* Mobile card view */}
      {pagedProps.length > 0 && (
        <div className="sm:hidden space-y-2">
          {pagedProps.map((prop, i) => {
            const edge = prop.edge;
            const edgeColor = edge > 0 ? "text-success" : edge < 0 ? "text-primary" : "text-muted-foreground";
            const signalColors: Record<string, string> = {
              STRONG: "bg-success/15 text-success border-success/30",
              LEAN: "bg-secondary/15 text-secondary border-secondary/30",
              PASS: "bg-muted text-muted-foreground border-border",
            };

            return (
              <div
                key={`mobile-${prop.player_name}-${prop.stat_type}-${page}-${i}`}
                className="card-surface rounded-sm p-3"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="min-w-0">
                    <span className="font-heading text-xs tracking-wider text-foreground truncate">
                      {prop.player_name}
                    </span>
                    <span className="text-[10px] text-muted-foreground ml-2">{prop.team}</span>
                  </div>
                  <span className={`text-[9px] font-heading px-1.5 py-0.5 border rounded-sm ${signalColors[prop.signal] ?? signalColors.PASS}`}>
                    {prop.signal}
                  </span>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[10px] font-heading font-semibold tracking-wider px-1.5 py-0.5 rounded-sm bg-secondary/15 text-secondary border border-secondary/30">
                    {prop.stat_type}
                  </span>
                  <span className="font-mono text-xs text-foreground">
                    Line: {prop.line}
                  </span>
                  <span className="font-mono text-xs text-foreground">
                    Proj: {prop.projection.toFixed(1)}
                  </span>
                  <span className={`font-mono text-xs ${edgeColor}`}>
                    {edge > 0 ? "+" : ""}{edge.toFixed(1)}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {prop.confidence}%
                  </span>
                </div>

                {onTrackBet && (
                  <button
                    onClick={() => handleTrackProp(prop)}
                    className="mt-2 w-full px-2 py-1.5 text-[10px] font-heading text-secondary border border-secondary/30 rounded-sm hover:bg-secondary/15 transition-colors text-center"
                  >
                    + TRACK
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-4">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1.5 text-xs font-heading tracking-wider text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
          >
            PREV
          </button>
          <span className="text-xs font-mono text-muted-foreground">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1.5 text-xs font-heading tracking-wider text-muted-foreground hover:text-foreground disabled:opacity-30 transition-colors"
          >
            NEXT
          </button>
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
