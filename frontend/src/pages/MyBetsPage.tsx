import { useState, useEffect, useRef } from "react";
import { Trash2 } from "lucide-react";
import { useGradeBets, useDeleteBet, useBetsCombined } from "@/hooks/use-bets";
import { toLowerSport, type Sport, type SportLower, type TrackedBet } from "@/lib/types";
import { LogoLoader } from "@/components/ui/LogoLoader";
import { toast } from "sonner";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { GaugeRing } from "@/components/jarvis/GaugeRing";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { GaugeSkeleton } from "@/components/jarvis/GaugeSkeleton";
import { CHART_COLORS } from "@/lib/chart-theme";

interface MyBetsPageProps {
  sport: Sport | null;
}

/* ── result color map ── */
const resultStyle: Record<string, { color: string; bg: string }> = {
  WIN:     { color: CHART_COLORS.green,   bg: `${CHART_COLORS.green}15` },
  LOSS:    { color: CHART_COLORS.crimson,  bg: `${CHART_COLORS.crimson}15` },
  PUSH:    { color: CHART_COLORS.gold,     bg: `${CHART_COLORS.gold}15` },
  PENDING: { color: CHART_COLORS.muted,    bg: `${CHART_COLORS.muted}15` },
};

/* ── sport hex badge color ── */
const sportHexColor: Record<string, string> = {
  nba: CHART_COLORS.crimson,
  nhl: "#60a5fa",
  mlb: CHART_COLORS.green,
  nfl: CHART_COLORS.gold,
  cbb: "#c084fc",
  cfb: "#f97316",
};

/* ── Bet Line Component ── */
function BetLine({ bet, onDelete }: { bet: TrackedBet; onDelete: (id: number) => void }) {
  const isSpread = bet.bet_type === "spread";
  const isProp = bet.bet_type === "prop";
  const rs = resultStyle[bet.result] ?? resultStyle.PENDING;

  return (
    <div className="flex items-start sm:items-center justify-between px-3 py-2.5 border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors gap-2">
      <div className="flex-1 min-w-0">
        {/* Row 1: sport hex + matchup */}
        <div className="flex items-center gap-2 flex-wrap">
          <HexBadge
            label={bet.sport.toUpperCase()}
            color={sportHexColor[bet.sport] ?? CHART_COLORS.muted}
            size="sm"
            active
          />
          <span className="font-mono text-xs text-foreground truncate">
            {bet.away_team} @ {bet.home_team}
          </span>
          {bet.recommendation && (
            <span className="text-[8px] font-heading tracking-widest uppercase px-1.5 py-0.5 border rounded-sm"
              style={{
                borderColor: `${CHART_COLORS.gold}40`,
                color: CHART_COLORS.gold,
                background: `${CHART_COLORS.gold}10`,
              }}
            >
              {bet.recommendation}
            </span>
          )}
        </div>

        {/* Row 2: pick details */}
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {isSpread && bet.lean_team && (
            <span className="font-mono text-xs" style={{ color: CHART_COLORS.gold }}>
              {bet.lean_team} {bet.spread_at_pick != null ? (bet.spread_at_pick > 0 ? `+${bet.spread_at_pick}` : bet.spread_at_pick) : ""}
            </span>
          )}
          {isProp && bet.player_name && (
            <span className="font-mono text-xs" style={{ color: CHART_COLORS.gold }}>
              {bet.player_name} {bet.stat_type} {bet.prop_direction === "OVER" ? "o" : "u"}{bet.prop_line}
            </span>
          )}
          {isProp && bet.projection != null && (
            <span className="text-[10px] text-muted-foreground font-mono">
              proj:{bet.projection.toFixed(1)}
            </span>
          )}
          {bet.cover_pct != null && (
            <span className="text-[10px] text-muted-foreground font-mono">
              {bet.cover_pct.toFixed(1)}%
            </span>
          )}
          {bet.actual_value != null && (
            <span className="text-[10px] font-mono text-foreground">
              actual:{bet.actual_value}
            </span>
          )}
        </div>

        {/* Row 3: date + score + clv */}
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-[10px] text-muted-foreground font-mono">
            {new Date(bet.created_at).toLocaleDateString()}
          </span>
          {bet.home_score != null && bet.away_score != null && (
            <span className="text-[10px] text-muted-foreground font-mono">
              {bet.away_score}-{bet.home_score}
            </span>
          )}
          {bet.clv != null && (
            <span className="text-[10px] font-mono" style={{ color: bet.clv > 0 ? CHART_COLORS.green : CHART_COLORS.crimson }}>
              CLV:{bet.clv > 0 ? "+" : ""}{bet.clv.toFixed(1)}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {/* Result hex badge */}
        <HexBadge label={bet.result} color={rs.color} size="sm" active />

        {bet.result === "PENDING" && (
          <button
            onClick={() => onDelete(bet.id)}
            className="p-1 text-muted-foreground hover:text-primary transition-colors"
          >
            <Trash2 className="w-3 h-3" />
          </button>
        )}
      </div>
    </div>
  );
}

/* ── Sport filter options ── */
const SPORT_FILTERS: { label: string; value: SportLower | undefined }[] = [
  { label: "ALL", value: undefined },
  { label: "NBA", value: "nba" },
  { label: "NHL", value: "nhl" },
  { label: "MLB", value: "mlb" },
  { label: "NFL", value: "nfl" },
  { label: "CBB", value: "cbb" },
  { label: "CFB", value: "cfb" },
];

export function MyBetsPage({ sport }: MyBetsPageProps) {
  const [sportFilter, setSportFilter] = useState<SportLower | undefined>(
    sport ? toLowerSport(sport) : undefined
  );
  const activeSport = sportFilter;
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");

  const { data: combinedData, isLoading } = useBetsCombined(activeSport, statusFilter, startDate || undefined, endDate || undefined);
  const bets = combinedData?.bets ?? [];
  const dashboard = combinedData?.dashboard;
  const gradeBets = useGradeBets();
  const deleteBet = useDeleteBet();

  // Auto-grade PENDING bets on page load (once per mount)
  const hasAutoGraded = useRef(false);
  useEffect(() => {
    if (hasAutoGraded.current) return;
    if (!bets.length) return;
    const hasPending = bets.some((b) => b.result === "PENDING");
    if (hasPending) {
      hasAutoGraded.current = true;
      gradeBets.mutate(undefined, {
        onSuccess: (data) => {
          if (data && data.graded > 0) {
            toast.success(`Graded ${data.graded} bets: ${data.wins}W/${data.losses}L/${data.pushes}P`);
          }
        },
      });
    }
  }, [bets]); // eslint-disable-line react-hooks/exhaustive-deps

  const statuses = ["ALL", "PENDING", "WIN", "LOSS", "PUSH"];
  const overall = dashboard?.overall;

  return (
    <div className="py-6 px-3 sm:px-6 max-w-5xl mx-auto space-y-4">
      {/* ── Page Header ── */}
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg sm:text-xl tracking-widest text-foreground uppercase">
          Field Log{" "}
          <span style={{ color: CHART_COLORS.crimson }}>/ Tracked Operations</span>
        </h2>
        <button
          onClick={() =>
            gradeBets.mutate(undefined, {
              onSuccess: (data) => {
                if (data && data.graded > 0) {
                  toast.success(`Graded ${data.graded} bets: ${data.wins}W/${data.losses}L/${data.pushes}P`);
                } else {
                  toast.info("No bets to grade");
                }
              },
            })
          }
          disabled={gradeBets.isPending}
          className="hud-btn px-4 py-1.5 text-[10px] font-heading tracking-widest uppercase"
          style={{
            borderColor: `${CHART_COLORS.crimson}50`,
            color: CHART_COLORS.crimson,
            background: `${CHART_COLORS.crimson}10`,
          }}
        >
          {gradeBets.isPending ? "GRADING..." : "GRADE ALL"}
        </button>
      </div>

      {/* ── Gauge Row ── */}
      {overall ? (
        <HudPanel title="FIELD METRICS" status="online">
          <div className="flex items-center justify-around flex-wrap gap-4 py-2">
            <GaugeRing
              value={overall.win_rate}
              max={100}
              label={`RECORD ${overall.wins}-${overall.losses}-${overall.pushes}`}
              unit="%"
              size={85}
              color={overall.win_rate >= 55 ? CHART_COLORS.green : overall.win_rate >= 50 ? CHART_COLORS.gold : CHART_COLORS.crimson}
            />
            <GaugeRing
              value={overall.win_rate}
              max={100}
              label="WIN RATE"
              unit="%"
              size={85}
              color={overall.win_rate >= 55 ? CHART_COLORS.green : CHART_COLORS.gold}
            />
            <GaugeRing
              value={Math.abs(overall.roi)}
              max={50}
              label="ROI"
              unit="%"
              size={85}
              color={overall.roi >= 0 ? CHART_COLORS.green : CHART_COLORS.crimson}
            />
            {/* CLV gauge if average CLV exists in any bet */}
            <GaugeRing
              value={overall.pending}
              max={Math.max(overall.pending, 20)}
              label="PENDING"
              unit=""
              size={85}
              color={CHART_COLORS.gold}
            />
          </div>
        </HudPanel>
      ) : isLoading ? (
        <HudPanel title="LOADING METRICS...">
          <div className="flex items-center justify-around gap-4 py-2">
            <GaugeSkeleton />
            <GaugeSkeleton />
            <GaugeSkeleton />
            <GaugeSkeleton />
          </div>
        </HudPanel>
      ) : null}

      {/* ── Sport Filter (HexBadge row) ── */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[9px] font-heading tracking-widest text-muted-foreground uppercase mr-1">SPORT:</span>
        {SPORT_FILTERS.map((sf) => (
          <HexBadge
            key={sf.label}
            label={sf.label}
            color={sf.value ? (sportHexColor[sf.value] ?? CHART_COLORS.muted) : CHART_COLORS.crimson}
            size="md"
            active={activeSport === sf.value}
            onClick={() => setSportFilter(sf.value)}
          />
        ))}
      </div>

      {/* ── Status Filter (angular buttons) ── */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[9px] font-heading tracking-widest text-muted-foreground uppercase mr-1">STATUS:</span>
        {statuses.map((s) => {
          const isActive = (s === "ALL" && !statusFilter) || statusFilter === s;
          const rs = resultStyle[s] ?? resultStyle.PENDING;
          return (
            <button
              key={s}
              onClick={() => setStatusFilter(s === "ALL" ? undefined : s)}
              className="px-3 py-1 text-[10px] font-heading tracking-widest uppercase border transition-all"
              style={{
                borderColor: isActive ? `${rs.color}60` : "hsla(0,0%,100%,0.06)",
                backgroundColor: isActive ? `${rs.color}15` : "transparent",
                color: isActive ? rs.color : CHART_COLORS.muted,
                clipPath: "polygon(6% 0%, 94% 0%, 100% 50%, 94% 100%, 6% 100%, 0% 50%)",
              }}
            >
              {s}
            </button>
          );
        })}
      </div>

      {/* ── Date Range Filter ── */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-[9px] font-heading tracking-widest text-muted-foreground uppercase">Date Range:</span>
        <input
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
          className="px-2 py-1 text-xs font-mono bg-transparent border border-white/10 text-foreground focus:border-white/20 outline-none"
        />
        <span className="text-muted-foreground text-[10px] font-heading tracking-widest">TO</span>
        <input
          type="date"
          value={endDate}
          onChange={(e) => setEndDate(e.target.value)}
          className="px-2 py-1 text-xs font-mono bg-transparent border border-white/10 text-foreground focus:border-white/20 outline-none"
        />
        {(startDate || endDate) && (
          <button
            onClick={() => { setStartDate(""); setEndDate(""); }}
            className="px-2 py-1 text-[9px] font-heading tracking-widest uppercase text-muted-foreground hover:text-foreground transition-colors"
          >
            CLEAR
          </button>
        )}
      </div>

      {/* ── Loading ── */}
      {isLoading && <LogoLoader text="LOADING FIELD LOG..." size="sm" />}

      {/* ── Bet List ── */}
      {bets.length > 0 && (
        <HudPanel title={`TRACKED OPERATIONS  [${bets.length}]`} status="online">
          {bets.map((bet) => (
            <BetLine key={bet.id} bet={bet} onDelete={(id) => deleteBet.mutate(id)} />
          ))}
        </HudPanel>
      )}

      {/* ── Empty state ── */}
      {!isLoading && bets.length === 0 && (
        <HudPanel title="NO OPERATIONS" status="offline">
          <p className="text-muted-foreground text-xs font-heading tracking-wider text-center py-8">
            No tracked operations found. Begin tracking from the Props or Picks interface.
          </p>
        </HudPanel>
      )}
    </div>
  );
}
