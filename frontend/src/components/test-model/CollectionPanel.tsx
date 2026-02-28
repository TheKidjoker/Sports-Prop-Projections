import { useTmCollect } from "@/hooks/use-test-model";
import { TmProgressBar } from "./TmProgressBar";
import { TmStatCards } from "./TmStatCards";
import type { SportLower } from "@/lib/types";

interface CollectionPanelProps {
  sport: SportLower;
}

export function CollectionPanel({ sport }: CollectionPanelProps) {
  const { start, status, features } = useTmCollect(sport);

  const progress = status.data?.progress;
  const isRunning = progress?.status === "running";
  const isComplete = progress?.status === "complete";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button
          onClick={() => start.mutate()}
          disabled={start.isPending || isRunning}
          className="px-4 py-2 bg-primary text-primary-foreground font-heading tracking-[0.12em] text-xs rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {isRunning ? "COLLECTING..." : "START COLLECTION"}
        </button>
        <button
          onClick={() => features.mutate()}
          disabled={features.isPending || isRunning}
          className="px-4 py-2 bg-secondary text-secondary-foreground font-heading tracking-[0.12em] text-xs rounded-sm hover:bg-secondary/90 transition-colors disabled:opacity-50"
        >
          {features.isPending ? "COMPUTING..." : "COMPUTE FEATURES"}
        </button>
      </div>

      {start.error && (
        <p className="text-xs text-red-400 font-mono">Error: {(start.error as Error).message}</p>
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

      {status.data && (
        <TmStatCards
          cards={[
            { label: "Total Games", value: status.data.total_games },
            { label: "With Spreads", value: status.data.games_with_spreads },
            {
              label: "Spread Coverage",
              value:
                status.data.total_games > 0
                  ? `${((status.data.games_with_spreads / status.data.total_games) * 100).toFixed(0)}%`
                  : "0%",
              color: status.data.games_with_spreads > 0 ? "green" : "yellow",
            },
            {
              label: "Status",
              value: progress?.status?.toUpperCase() ?? "IDLE",
              color: isComplete ? "green" : isRunning ? "yellow" : "default",
            },
          ]}
        />
      )}

      {features.isSuccess && features.data && (
        <div className="card-surface rounded-sm p-3">
          <p className="text-xs text-green-400 font-mono">
            Features computed: {features.data.features_computed}
          </p>
        </div>
      )}

      {features.error && (
        <p className="text-xs text-red-400 font-mono">
          Feature error: {(features.error as Error).message}
        </p>
      )}
    </div>
  );
}
