import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, ChevronUp } from "lucide-react";
import { useSaveBets } from "@/hooks/use-bets";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { toast } from "sonner";

export interface BetSlipItem {
  event_id: string;
  sport: string;
  type: "spread" | "prop";
  team: string;
  stat?: string;
  line: number;
  label: string;
  home_team?: string;
  away_team?: string;
  game_date?: string;
  recommendation?: string;
  cover_pct?: number;
  slot_type?: string;
  action?: string;
  player_name?: string;
  direction?: string;
  projection?: number;
  edge?: number;
  confidence?: number;
  signal?: string;
}

interface BetSlipProps {
  bets: BetSlipItem[];
  onRemove: (index: number) => void;
  onClear: () => void;
}

export function BetSlip({ bets, onRemove, onClear }: BetSlipProps) {
  const saveMutation = useSaveBets();
  const [wager, setWager] = useState(100);
  const [expanded, setExpanded] = useState(true);

  if (bets.length === 0) return null;

  const handleConfirm = () => {
    const payload = bets.map((b) => ({
      bet_type: b.type,
      sport: b.sport,
      event_id: b.event_id,
      game_date: b.game_date || new Date().toISOString().slice(0, 10),
      home_team: b.home_team || "",
      away_team: b.away_team || "",
      lean_team: b.type === "spread" ? b.team : null,
      spread_at_pick: b.type === "spread" ? b.line : null,
      action: b.action || null,
      recommendation: b.recommendation || null,
      cover_pct: b.cover_pct || null,
      slot_type: b.slot_type || null,
      player_name: b.player_name || "",
      stat_type: b.stat || "",
      prop_line: b.type === "prop" ? b.line : null,
      prop_direction: b.direction || (b.edge && b.edge > 0 ? "OVER" : "UNDER"),
      projection: b.projection || null,
      edge: b.edge || null,
      confidence: b.confidence || null,
      signal: b.signal || null,
    }));
    saveMutation.mutate(payload, {
      onSuccess: () => {
        toast.success(`${payload.length} operation${payload.length > 1 ? "s" : ""} deployed`);
        onClear();
      },
      onError: (err) => {
        toast.error(`Deploy failed: ${err instanceof Error ? err.message : "Unknown error"}`);
      },
    });
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ x: 400, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 400, opacity: 0 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        className="fixed bottom-20 right-2 left-2 sm:left-auto sm:right-4 md:bottom-4 z-50 sm:w-80"
      >
        <div className="hud-panel hud-panel-active shadow-lg">
          {/* Header */}
          <div className="hud-panel-header justify-between">
            <div className="flex items-center gap-2">
              <span className="text-foreground">ACTIVE OPERATIONS</span>
              <span className="font-mono text-primary text-[10px]">({bets.length})</span>
            </div>
            <div className="flex items-center gap-1">
              <button onClick={() => setExpanded(!expanded)} className="text-muted-foreground hover:text-foreground transition-colors">
                <ChevronUp className={`w-3.5 h-3.5 transition-transform ${expanded ? "" : "rotate-180"}`} />
              </button>
              <button onClick={onClear} className="text-muted-foreground hover:text-foreground transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {expanded && (
            <>
              {/* Bet rows */}
              <div className="max-h-48 overflow-y-auto">
                {bets.map((bet, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-2 border-b border-border/30 hover:bg-muted/20 transition-colors">
                    <div className="flex-1 min-w-0 flex items-center gap-2">
                      <HexBadge label={bet.sport.toUpperCase().slice(0, 3)} size="sm" active />
                      <span className="font-mono text-[10px] text-foreground truncate">{bet.label}</span>
                    </div>
                    <button
                      onClick={() => onRemove(i)}
                      className="p-1 text-muted-foreground hover:text-primary transition-colors flex-shrink-0"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>

              {/* Wager + Deploy */}
              <div className="px-4 py-3 border-t border-border/30">
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-[10px] font-heading tracking-wider text-muted-foreground">WAGER</span>
                  <input
                    type="number"
                    value={wager}
                    onChange={(e) => setWager(Number(e.target.value))}
                    className="w-20 px-2 py-1 bg-muted border border-border text-xs font-mono text-foreground focus:border-primary focus:outline-none transition-colors"
                    style={{ clipPath: "polygon(0 3px, 3px 0, 100% 0, 100% calc(100% - 3px), calc(100% - 3px) 100%, 0 100%)" }}
                  />
                </div>
                <button
                  onClick={handleConfirm}
                  disabled={saveMutation.isPending}
                  className="w-full py-2.5 text-xs font-heading tracking-[0.15em] bg-primary text-primary-foreground transition-all duration-200 hover:bg-primary/90 active:scale-[0.98] disabled:opacity-50"
                  style={{ clipPath: "polygon(0 4px, 4px 0, calc(100% - 4px) 0, 100% 4px, 100% calc(100% - 4px), calc(100% - 4px) 100%, 4px 100%, 0 calc(100% - 4px))" }}
                >
                  {saveMutation.isPending ? "DEPLOYING..." : "DEPLOY"}
                </button>
              </div>
            </>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
