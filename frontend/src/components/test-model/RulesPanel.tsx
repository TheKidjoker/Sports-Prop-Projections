import { useEffect } from "react";
import { useTmRulesReplay } from "@/hooks/use-test-model";
import { TmProgressBar } from "./TmProgressBar";
import { TmStatCards } from "./TmStatCards";
import { TmThresholdTable } from "./TmThresholdTable";
import { TmFactorBreakdown } from "./TmFactorBreakdown";
import { TmComparisonTable } from "./TmComparisonTable";
import { TmFactorHealthReport } from "./TmFactorHealthReport";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SportLower } from "@/lib/types";

interface RulesPanelProps {
  sport: SportLower;
}

export function RulesPanel({ sport }: RulesPanelProps) {
  const { start, status, metrics } = useTmRulesReplay(sport);
  const progress = status.data?.progress;
  const isRunning = progress?.status === "running";
  const isComplete = progress?.status === "complete";

  // Auto-load metrics when backtest completes
  useEffect(() => {
    if (isComplete) {
      metrics.refetch();
    }
  }, [isComplete]); // eslint-disable-line react-hooks/exhaustive-deps

  const rulesParams = metrics.data?.rules_metrics?.model_params;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => start.mutate()}
          disabled={start.isPending || isRunning}
          className="px-4 py-2 bg-primary text-primary-foreground font-heading tracking-[0.12em] text-xs rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          {isRunning ? "RUNNING..." : "RUN RULES REPLAY"}
        </button>
        <button
          onClick={() => metrics.refetch()}
          disabled={metrics.isFetching}
          className="px-3 py-2 border border-border text-foreground font-heading tracking-[0.12em] text-xs rounded-sm hover:bg-muted transition-colors disabled:opacity-50"
        >
          {metrics.isFetching ? "LOADING..." : "LOAD METRICS"}
        </button>
      </div>

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

      {rulesParams && (
        <>
          {/* Comparison table */}
          {rulesParams.comparison && (
            <TmComparisonTable comparison={rulesParams.comparison} />
          )}

          {/* Summary stats */}
          <TmStatCards
            cards={[
              { label: "Total Games", value: rulesParams.total_games ?? 0 },
              { label: "Qualified", value: rulesParams.total_qualified ?? 0 },
              {
                label: "Accuracy",
                value: rulesParams.accuracy != null ? `${rulesParams.accuracy.toFixed(1)}%` : "—",
                color: (rulesParams.accuracy ?? 0) >= 55 ? "green" : "red",
              },
              {
                label: "ROI",
                value: rulesParams.roi != null
                  ? `${rulesParams.roi > 0 ? "+" : ""}${rulesParams.roi.toFixed(1)}%`
                  : "—",
                color: (rulesParams.roi ?? 0) > 0 ? "green" : "red",
              },
            ]}
          />

          {/* CLV by tier (if available) */}
          {rulesParams.clv_avg != null && (
            <div className="card-surface rounded-sm p-3">
              <span className="text-xs text-muted-foreground font-heading tracking-wider">CLV AVG: </span>
              <span className={`font-mono text-sm ${rulesParams.clv_avg > 0 ? "text-green-400" : "text-red-400"}`}>
                {rulesParams.clv_avg > 0 ? "+" : ""}{rulesParams.clv_avg.toFixed(2)}
              </span>
            </div>
          )}

          {/* Threshold table */}
          {rulesParams.by_threshold && (
            <TmThresholdTable rows={rulesParams.by_threshold} title="Score Threshold Analysis" />
          )}

          {/* Factor breakdown */}
          {rulesParams.by_factor && (
            <TmFactorBreakdown factors={rulesParams.by_factor} />
          )}

          {/* Slot breakdown */}
          {rulesParams.by_slot && rulesParams.by_slot.length > 0 && (
            <div>
              <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-2 uppercase">
                By Slot Type
              </h4>
              <div className="rounded-sm border border-border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="text-xs font-heading tracking-wider">Slot</TableHead>
                      <TableHead className="text-xs font-heading tracking-wider text-right">Count</TableHead>
                      <TableHead className="text-xs font-heading tracking-wider text-right">Accuracy</TableHead>
                      <TableHead className="text-xs font-heading tracking-wider text-right">ROI</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rulesParams.by_slot.map((s) => (
                      <TableRow key={s.slot}>
                        <TableCell className="font-mono text-sm">{s.slot}</TableCell>
                        <TableCell className="font-mono text-sm text-right">{s.count}</TableCell>
                        <TableCell
                          className={`font-mono text-sm text-right ${
                            s.accuracy >= 55 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {s.accuracy.toFixed(1)}%
                        </TableCell>
                        <TableCell
                          className={`font-mono text-sm text-right ${
                            s.roi > 0 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {s.roi > 0 ? "+" : ""}
                          {s.roi.toFixed(1)}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}

          {/* Recommendation breakdown */}
          {rulesParams.by_recommendation && rulesParams.by_recommendation.length > 0 && (
            <div>
              <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-2 uppercase">
                By Recommendation
              </h4>
              <div className="rounded-sm border border-border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="text-xs font-heading tracking-wider">Rec</TableHead>
                      <TableHead className="text-xs font-heading tracking-wider text-right">Count</TableHead>
                      <TableHead className="text-xs font-heading tracking-wider text-right">Accuracy</TableHead>
                      <TableHead className="text-xs font-heading tracking-wider text-right">ROI</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {rulesParams.by_recommendation.map((r) => (
                      <TableRow key={r.recommendation}>
                        <TableCell className="font-mono text-sm">{r.recommendation}</TableCell>
                        <TableCell className="font-mono text-sm text-right">{r.count}</TableCell>
                        <TableCell
                          className={`font-mono text-sm text-right ${
                            r.accuracy >= 55 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {r.accuracy.toFixed(1)}%
                        </TableCell>
                        <TableCell
                          className={`font-mono text-sm text-right ${
                            r.roi > 0 ? "text-green-400" : "text-red-400"
                          }`}
                        >
                          {r.roi > 0 ? "+" : ""}
                          {r.roi.toFixed(1)}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}

          {/* Factor health report */}
          {rulesParams.factor_health && (
            <TmFactorHealthReport health={rulesParams.factor_health} />
          )}
        </>
      )}

      {metrics.isSuccess && !rulesParams && (
        <p className="text-xs text-muted-foreground font-mono">
          No rules backtest data — run Rules Replay first.
        </p>
      )}
    </div>
  );
}
