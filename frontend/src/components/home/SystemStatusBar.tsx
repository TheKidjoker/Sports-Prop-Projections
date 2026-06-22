import { useState, useEffect } from "react";
import { StatusIndicator } from "@/components/jarvis/StatusIndicator";

export function SystemStatusBar({ totalGames }: { totalGames: number }) {
  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="hud-panel flex items-center justify-between px-4 py-2">
      <StatusIndicator status="online" label="SYSTEM ONLINE" />
      <span className="font-mono text-[10px] text-muted-foreground">
        {time.toLocaleTimeString("en-US", { hour12: false })} EST
      </span>
      <span className="font-heading text-[10px] tracking-wider text-muted-foreground">
        <span className="text-foreground font-mono">{totalGames}</span> ACTIVE OPERATIONS
      </span>
    </div>
  );
}
