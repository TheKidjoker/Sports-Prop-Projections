import { useTmBacktest } from "@/hooks/use-test-model";
import { TmProgressBar } from "./TmProgressBar";
import type { SportLower } from "@/lib/types";

interface BacktestPanelProps {
  sport: SportLower;
}

export function BacktestPanel({ sport }: BacktestPanelProps) {
  const { start, status } = useTmBacktest(sport);
  const progress = status.data?.progress;
  const isRunning = progress?.status === "running";
  const isComplete = progress?.status === "complete";

  return (
    <div className="space-y-4">
      <button
        onClick={() => start.mutate()}
        disabled={start.isPending || isRunning}
        className="px-4 py-2 bg-primary text-primary-foreground font-heading tracking-[0.12em] text-xs rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
      >
        {isRunning ? "RUNNING..." : "RUN BACKTEST"}
      </button>

      {start.error && (
        <p className="text-xs text-red-400 font-mono">
          Error: {(start.error as Error).message}
        </p>
      )}

      {(isRunning || isComplete) && progress && (
        <TmProgressBar
          pct={progress.pct ?? (isComplete ? 100 : 0)}
          status={progress.status}
          message={progress.message}
        />
      )}

      {progress?.error && (
        <p className="text-xs text-red-400 font-mono">Error: {progress.error}</p>
      )}

      {isComplete && progress?.metrics && (
        <div className="card-surface rounded-sm p-4">
          <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-2 uppercase">
            Backtest Results
          </h4>
          <pre className="text-xs font-mono text-muted-foreground overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(progress.metrics, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
