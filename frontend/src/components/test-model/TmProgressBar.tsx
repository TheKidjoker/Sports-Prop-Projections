import { Progress } from "@/components/ui/progress";

interface TmProgressBarProps {
  pct: number;
  status: string;
  message?: string;
}

export function TmProgressBar({ pct, status, message }: TmProgressBarProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="font-heading tracking-wider text-muted-foreground uppercase">
          {status === "running" ? "PROCESSING" : status?.toUpperCase() ?? "IDLE"}
        </span>
        <span className="font-mono text-muted-foreground">{Math.round(pct)}%</span>
      </div>
      <Progress value={pct} className="h-2" />
      {message && (
        <p className="text-xs text-muted-foreground font-mono truncate">{message}</p>
      )}
    </div>
  );
}
