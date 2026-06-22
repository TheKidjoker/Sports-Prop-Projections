import { useState, useMemo, useEffect } from "react";
import { useTopProps } from "@/hooks/use-props";
import { LogoLoader } from "@/components/ui/LogoLoader";
import { toLowerSport, type Sport, type PropSignal } from "@/lib/types";
import type { BetSlipItem } from "@/components/bets/BetSlip";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { StatusIndicator } from "@/components/jarvis/StatusIndicator";
import { TableRowSkeleton } from "@/components/jarvis/TableRowSkeleton";
import { CHART_COLORS } from "@/lib/chart-theme";

const PROPS_PER_PAGE = 25;

interface PropsPageProps {
  sport: Sport | null;
  onTrackBet?: (bet: BetSlipItem) => void;
}

/* ── signal color map ── */
const signalColor: Record<string, string> = {
  STRONG: CHART_COLORS.green,
  LEAN: CHART_COLORS.gold,
  PASS: CHART_COLORS.muted,
};

/* ── stat-type hex badge color ── */
const statColor = CHART_COLORS.gold;

export function PropsPage({ sport, onTrackBet }: PropsPageProps) {
  const [page, setPage] = useState(0);
  const activeSport = sport ? toLowerSport(sport) : "nba";
  const propsAvailable = activeSport === "nba" || activeSport === "nhl" || activeSport === "cbb" || activeSport === "mlb";

  // Auto-load props (cache-only on backend, so this is fast)
  const { data, isLoading, error, refetch } = useTopProps(activeSport, propsAvailable);
  const isRefreshing = data?.refreshing === true && (!data?.props || data.props.length === 0);

  // Reset page when sport changes
  useEffect(() => { setPage(0); }, [activeSport]);

  // Auto-retry when backend is computing props in background
  useEffect(() => {
    if (!isRefreshing) return;
    const timer = setTimeout(() => refetch(), 8000);
    return () => clearTimeout(timer);
  }, [isRefreshing, refetch]);

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

  /* ── edge mini-bar helper ── */
  const EdgeBar = ({ edge }: { edge: number }) => {
    const absEdge = Math.min(Math.abs(edge), 10);
    const pct = (absEdge / 10) * 100;
    const color = edge > 0 ? CHART_COLORS.green : CHART_COLORS.crimson;
    return (
      <div className="w-14 flex items-center gap-1">
        <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: color }} />
        </div>
        <span className="font-mono text-[10px] tabular-nums" style={{ color }}>
          {edge > 0 ? "+" : ""}{edge.toFixed(1)}
        </span>
      </div>
    );
  };

  return (
    <div className="py-6 px-3 sm:px-6 max-w-5xl mx-auto space-y-4">
      {/* ── Page Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="font-heading text-lg sm:text-xl tracking-widest text-foreground uppercase">
            Operative Intelligence{" "}
            <span style={{ color: CHART_COLORS.crimson }}>/ Player Props</span>
          </h2>
          <StatusIndicator status={propsAvailable ? "online" : "offline"} label={propsAvailable ? "ACTIVE" : "UNAVAILABLE"} />
        </div>
        {propsAvailable && (
          <button
            onClick={() => { setPage(0); refetch(); }}
            disabled={isLoading}
            className="hud-btn px-4 py-1.5 text-[10px] font-heading tracking-widest uppercase"
            style={{
              borderColor: `${CHART_COLORS.crimson}50`,
              color: CHART_COLORS.crimson,
              background: `${CHART_COLORS.crimson}10`,
            }}
          >
            {isLoading ? "SCANNING..." : "REFRESH"}
          </button>
        )}
      </div>

      {/* ── Not available notice ── */}
      {!propsAvailable && (
        <HudPanel title="SYSTEM NOTICE" status="warning">
          <p className="text-muted-foreground text-xs font-heading tracking-wider text-center py-4">
            Props intelligence available for NBA, NHL, CBB, and MLB theatres only
          </p>
        </HudPanel>
      )}

      {/* ── Error ── */}
      {error && (
        <HudPanel title="ALERT" status="error">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono" style={{ color: CHART_COLORS.crimson }}>
              {(error as Error).message}
            </span>
            <button
              onClick={() => refetch()}
              className="text-[10px] font-heading tracking-widest uppercase hover:underline"
              style={{ color: CHART_COLORS.crimson }}
            >
              RETRY
            </button>
          </div>
        </HudPanel>
      )}

      {/* ── Loading states ── */}
      {isLoading && <LogoLoader text="ACQUIRING PROP INTELLIGENCE..." />}

      {isRefreshing && !isLoading && (
        <div className="text-center py-6">
          <LogoLoader text="COMPUTING PROJECTIONS..." />
          <p className="text-muted-foreground text-[10px] font-heading tracking-widest mt-2">
            Server-side computation in progress. Auto-refreshing...
          </p>
        </div>
      )}

      {/* ── Desktop Table ── */}
      {pagedProps.length > 0 && (
        <HudPanel title={`PROP SIGNALS  [${sortedProps.length}]`} status="online" className="hidden sm:block">
          {/* Angular header row */}
          <div className="flex items-center gap-3 px-2 py-1.5 border-b border-white/[0.06] text-[9px] font-heading tracking-widest text-muted-foreground uppercase">
            <div className="flex-1">OPERATIVE</div>
            <span className="w-14 text-center">TYPE</span>
            <span className="w-10 text-right">LINE</span>
            <span className="w-12 text-right">PROJ</span>
            <span className="w-20 text-right">EDGE</span>
            <span className="w-14 text-center">SIGNAL</span>
            <span className="w-8 text-right">CONF</span>
            <span className="w-7" />
          </div>

          {/* Data rows */}
          {pagedProps.map((prop, i) => (
            <div
              key={`${prop.player_name}-${prop.stat_type}-${page}-${i}`}
              className="flex items-center gap-3 px-2 py-2 border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors"
            >
              {/* Player */}
              <div className="flex-1 min-w-0">
                <span className="font-heading text-xs tracking-wider text-foreground truncate block">
                  {prop.player_name}
                </span>
                <span className="text-[9px] text-muted-foreground font-mono">{prop.team} vs {prop.opponent}</span>
              </div>

              {/* Stat type hex badge */}
              <span className="w-14 flex justify-center">
                <HexBadge label={prop.stat_type} color={statColor} size="sm" active />
              </span>

              {/* Line */}
              <span className="font-mono text-xs text-foreground w-10 text-right tabular-nums">
                {prop.line}
              </span>

              {/* Projection */}
              <span className="font-mono text-xs text-foreground w-12 text-right tabular-nums">
                {prop.projection.toFixed(1)}
              </span>

              {/* Edge mini bar */}
              <span className="w-20 flex justify-end">
                <EdgeBar edge={prop.edge} />
              </span>

              {/* Signal badge */}
              <span className="w-14 flex justify-center">
                <HexBadge
                  label={prop.signal}
                  color={signalColor[prop.signal] ?? CHART_COLORS.muted}
                  size="sm"
                  active
                />
              </span>

              {/* Confidence */}
              <span className="font-mono text-[10px] text-muted-foreground w-8 text-right tabular-nums">
                {prop.confidence}
              </span>

              {/* Track button */}
              <span className="w-7 flex justify-center">
                {onTrackBet && (
                  <button
                    onClick={() => handleTrackProp(prop)}
                    className="w-5 h-5 flex items-center justify-center text-[10px] font-heading border rounded-sm transition-all hover:scale-110"
                    style={{
                      borderColor: `${CHART_COLORS.crimson}50`,
                      color: CHART_COLORS.crimson,
                    }}
                  >
                    +
                  </button>
                )}
              </span>
            </div>
          ))}
        </HudPanel>
      )}

      {/* ── Loading skeleton ── */}
      {isLoading && (
        <div className="hidden sm:block">
          <HudPanel title="LOADING SIGNALS...">
            {Array.from({ length: 8 }).map((_, i) => (
              <TableRowSkeleton key={i} cols={7} />
            ))}
          </HudPanel>
        </div>
      )}

      {/* ── Mobile Cards ── */}
      {pagedProps.length > 0 && (
        <div className="sm:hidden space-y-2">
          {pagedProps.map((prop, i) => (
            <HudPanel key={`mobile-${prop.player_name}-${prop.stat_type}-${page}-${i}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="min-w-0 flex items-center gap-2">
                  <span className="font-heading text-xs tracking-wider text-foreground truncate">
                    {prop.player_name}
                  </span>
                  <span className="text-[9px] text-muted-foreground font-mono">{prop.team}</span>
                </div>
                <HexBadge
                  label={prop.signal}
                  color={signalColor[prop.signal] ?? CHART_COLORS.muted}
                  size="sm"
                  active
                />
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <HexBadge label={prop.stat_type} color={statColor} size="sm" active />
                <span className="font-mono text-xs text-foreground tabular-nums">
                  L:{prop.line}
                </span>
                <span className="font-mono text-xs text-foreground tabular-nums">
                  P:{prop.projection.toFixed(1)}
                </span>
                <EdgeBar edge={prop.edge} />
                <span className="font-mono text-[10px] text-muted-foreground tabular-nums">
                  {prop.confidence}%
                </span>
              </div>

              {onTrackBet && (
                <button
                  onClick={() => handleTrackProp(prop)}
                  className="mt-2 w-full py-1.5 text-[10px] font-heading tracking-widest uppercase border transition-all hover:bg-white/[0.03]"
                  style={{
                    borderColor: `${CHART_COLORS.crimson}40`,
                    color: CHART_COLORS.crimson,
                  }}
                >
                  + TRACK OPERATIVE
                </button>
              )}
            </HudPanel>
          ))}
        </div>
      )}

      {/* ── Pagination ── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4 pt-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-4 py-1.5 text-[10px] font-heading tracking-widest uppercase border border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20 disabled:opacity-20 transition-all"
          >
            &laquo; PREV
          </button>
          <span className="font-mono text-xs text-muted-foreground tabular-nums">
            {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-4 py-1.5 text-[10px] font-heading tracking-widest uppercase border border-white/10 text-muted-foreground hover:text-foreground hover:border-white/20 disabled:opacity-20 transition-all"
          >
            NEXT &raquo;
          </button>
        </div>
      )}

      {/* ── Empty state ── */}
      {!isLoading && !isRefreshing && sortedProps.length === 0 && propsAvailable && (
        <HudPanel title="NO SIGNALS" status="offline">
          <p className="text-muted-foreground text-xs font-heading tracking-wider text-center py-6">
            No prop intelligence available at this time. Standby for next scan window.
          </p>
        </HudPanel>
      )}
    </div>
  );
}
