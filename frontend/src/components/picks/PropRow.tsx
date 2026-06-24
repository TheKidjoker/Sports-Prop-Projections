import { Badge } from "@/components/ui/badge";
import type { PropSignal } from "@/lib/types";

const signalBadgeVariant = (signal: string): "signal-strong" | "signal-lean" | "signal-pass" => {
  switch (signal) {
    case "STRONG": return "signal-strong";
    case "LEAN": return "signal-lean";
    default: return "signal-pass";
  }
};

interface PropRowProps {
  prop: PropSignal;
  onTrack?: (prop: PropSignal) => void;
}

export function PropRow({ prop, onTrack }: PropRowProps) {
  const edge = prop.edge;
  const edgeColor = edge > 0 ? "text-success" : edge < 0 ? "text-primary" : "text-muted-foreground";

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-b border-border/30 hover:bg-muted/20 transition-colors">
      <div className="flex-1 min-w-0">
        <span className="font-heading text-xs tracking-wider text-foreground truncate">
          {prop.player_name}
        </span>
        <span className="text-[13px] text-muted-foreground ml-2">{prop.team}</span>
      </div>

      <span className="text-[13px] font-heading font-semibold tracking-wider px-1.5 py-0.5 rounded-sm bg-secondary/15 text-secondary border border-secondary/30 w-12 text-center">
        {prop.stat_type}
      </span>

      <span className="font-mono text-xs text-foreground w-10 text-right">
        {prop.line}
      </span>

      <span className="font-mono text-xs text-foreground w-12 text-right">
        {prop.projection.toFixed(1)}
      </span>

      <span className={`font-mono text-xs w-14 text-right ${edgeColor}`}>
        {edge > 0 ? "+" : ""}{edge.toFixed(1)}
      </span>

      <Badge variant={signalBadgeVariant(prop.signal)} size="sm">
        {prop.signal}
      </Badge>

      <span className="font-mono text-[13px] text-muted-foreground w-8 text-right">
        {prop.confidence}
      </span>

      {onTrack && (
        <button
          onClick={() => onTrack(prop)}
          className="px-1.5 py-0.5 text-[13px] font-heading text-secondary border border-secondary/30 rounded-sm hover:bg-secondary/15 transition-colors"
        >
          +
        </button>
      )}
    </div>
  );
}
