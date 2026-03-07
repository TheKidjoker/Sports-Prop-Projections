import { useState } from "react";
import { X } from "lucide-react";
import { useSaveBets } from "@/hooks/use-bets";
import { toast } from "sonner";

export interface BetSlipItem {
  event_id: string;
  sport: string;
  type: "spread" | "prop";
  team: string;
  stat?: string;
  line: number;
  label: string;
  // Extra fields for backend persistence
  home_team?: string;
  away_team?: string;
  game_date?: string;
  recommendation?: string;
  cover_pct?: number;
  slot_type?: string;
  action?: string;
  // Prop-specific
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
        toast.success(`${payload.length} bet${payload.length > 1 ? "s" : ""} saved`);
        onClear();
      },
      onError: (err) => {
        toast.error(`Failed to save: ${err instanceof Error ? err.message : "Unknown error"}`);
      },
    });
  };

  return (
    <div className="fixed bottom-20 right-2 left-2 sm:left-auto sm:right-4 lg:bottom-4 z-50 sm:w-80 card-surface rounded-sm shadow-lg border border-border">
      <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-muted/30">
        <span className="font-heading text-xs tracking-wider text-foreground">
          MY PICKS ({bets.length})
        </span>
        <button onClick={onClear} className="text-muted-foreground hover:text-foreground transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="max-h-48 overflow-y-auto">
        {bets.map((bet, i) => (
          <div key={i} className="flex items-center justify-between px-4 py-2 border-b border-border/30">
            <div className="flex-1 min-w-0">
              <span className="text-[10px] text-muted-foreground uppercase">{bet.sport} </span>
              <span className="font-mono text-xs text-foreground truncate">{bet.label}</span>
            </div>
            <button
              onClick={() => onRemove(i)}
              className="p-1 text-muted-foreground hover:text-primary transition-colors"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}
      </div>

      <div className="px-4 py-3 border-t border-border">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[10px] font-heading text-muted-foreground">WAGER</span>
          <input
            type="number"
            value={wager}
            onChange={(e) => setWager(Number(e.target.value))}
            className="w-20 px-2 py-1 bg-muted border border-border rounded-sm text-xs font-mono text-foreground"
          />
        </div>
        <button
          onClick={handleConfirm}
          disabled={saveMutation.isPending}
          className="w-full py-2 text-xs font-heading tracking-wider bg-primary text-primary-foreground rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {saveMutation.isPending ? "SAVING..." : "CONFIRM BETS"}
        </button>
      </div>
    </div>
  );
}
