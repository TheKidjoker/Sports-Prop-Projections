import { HudPanel } from "@/components/jarvis/HudPanel";
import type { DashboardRecent } from "@/lib/types";

interface RecentMissionLogProps {
  recent?: DashboardRecent[];
}

export function RecentMissionLog({ recent }: RecentMissionLogProps) {
  if (!recent || recent.length === 0) return null;

  const items = recent.slice(0, 15);

  return (
    <HudPanel title="RECENT OPERATIONS" status="online">
      <div className="space-y-0.5 max-h-[300px] overflow-y-auto">
        {items.map((pred) => {
          const statusMap: Record<string, "success" | "error" | "pending"> = { HIT: "success", MISS: "error", PUSH: "pending" };
          const statusColor: Record<string, string> = {
            HIT: "bg-success/15 text-success border-success/30",
            MISS: "bg-primary/15 text-primary border-primary/30",
            PUSH: "bg-warning/15 text-warning border-warning/30",
          };
          const status = statusMap[pred.result] ?? "pending";
          return (
            <div key={pred.event_id} className="flex items-center gap-2 px-2 py-1.5 hover:bg-muted/20 transition-colors">
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${status === "success" ? "bg-success" : status === "error" ? "bg-primary" : "bg-muted-foreground"}`} />
              <span className="text-[10px] font-heading tracking-wider text-muted-foreground w-8 flex-shrink-0">
                {pred.sport?.toUpperCase().slice(0, 3)}
              </span>
              <span className="font-mono text-[10px] text-foreground truncate flex-1">
                {pred.away_team} @ {pred.home_team}
              </span>
              <span className="font-mono text-[10px] text-muted-foreground flex-shrink-0">
                {pred.cover_pct?.toFixed(0)}%
              </span>
              <span className={`text-[8px] font-heading tracking-wider px-1.5 py-0.5 border rounded-sm flex-shrink-0 ${statusColor[pred.result] ?? "bg-muted text-muted-foreground border-border"}`}>
                {pred.result || "PENDING"}
              </span>
            </div>
          );
        })}
      </div>
    </HudPanel>
  );
}
