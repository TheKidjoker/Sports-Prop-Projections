import { useEffect } from "react";
import { useTmMetrics, useTmEvTrain } from "@/hooks/use-test-model";
import { TmStatCards } from "./TmStatCards";
import { TmProgressBar } from "./TmProgressBar";
import { TmFeatureImportances } from "./TmFeatureImportances";
import type { SportLower } from "@/lib/types";

interface MetricsPanelProps {
  sport: SportLower;
}

const EV_SPORTS: SportLower[] = ["nba", "nhl", "cbb"];

export function MetricsPanel({ sport }: MetricsPanelProps) {
  const metricsQ = useTmMetrics(sport);
  const ev = useTmEvTrain(sport);

  const hasEv = EV_SPORTS.includes(sport);
  const evProgress = ev.status.data?.progress;
  const evRunning = evProgress?.status === "running";
  const evComplete = evProgress?.status === "complete";

  // Auto-fetch EV metrics when training completes
  useEffect(() => {
    if (evComplete) {
      ev.metrics.refetch();
    }
  }, [evComplete]);

  const d = metricsQ.data;

  return (
    <div className="space-y-6">
      {metricsQ.isLoading && (
        <p className="text-xs text-muted-foreground font-heading tracking-wider animate-pulse">
          LOADING METRICS...
        </p>
      )}

      {metricsQ.error && (
        <p className="text-xs text-red-400 font-mono">
          Error: {(metricsQ.error as Error).message}
        </p>
      )}

      {d && (
        <>
          <TmStatCards
            cards={[
              { label: "Total Games", value: d.total_games },
              { label: "Total Features", value: d.total_features },
              {
                label: "Feature Coverage",
                value:
                  d.total_games > 0
                    ? `${((d.total_features / d.total_games) * 100).toFixed(0)}%`
                    : "0%",
                color: d.total_features > 0 ? "green" : "yellow",
              },
            ]}
          />

          {d.metrics && (
            <div className="card-surface rounded-sm p-4">
              <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-2 uppercase">
                Latest Backtest
              </h4>
              <pre className="text-xs font-mono text-muted-foreground overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(d.metrics, null, 2)}
              </pre>
            </div>
          )}
        </>
      )}

      {hasEv && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <h4 className="font-heading text-xs tracking-[0.15em] text-foreground uppercase">
              EV MODEL ({sport.toUpperCase()})
            </h4>
            <button
              onClick={() => ev.start.mutate()}
              disabled={ev.start.isPending || evRunning}
              className="px-3 py-1.5 bg-primary text-primary-foreground font-heading tracking-[0.12em] text-[10px] rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {evRunning ? "TRAINING..." : "TRAIN EV MODEL"}
            </button>
            <button
              onClick={() => ev.metrics.refetch()}
              className="px-3 py-1.5 border border-border text-foreground font-heading tracking-[0.12em] text-[10px] rounded-sm hover:bg-muted transition-colors"
            >
              LOAD METRICS
            </button>
          </div>

          {(evRunning || evProgress?.status === "complete") && evProgress && (
            <TmProgressBar
              pct={evProgress.pct ?? (evProgress.status === "complete" ? 100 : 0)}
              status={evProgress.status}
              message={evProgress.message}
            />
          )}

          {ev.metrics.data?.ev_metrics?.model_params && (
            <div className="space-y-4">
              <TmStatCards
                cards={[
                  {
                    label: "AUC",
                    value: ev.metrics.data.ev_metrics.model_params.auc?.toFixed(3) ?? "N/A",
                    color: (ev.metrics.data.ev_metrics.model_params.auc ?? 0) >= 0.54 ? "green" : "red",
                  },
                  {
                    label: "Accuracy",
                    value: ev.metrics.data.ev_metrics.model_params.accuracy
                      ? `${(ev.metrics.data.ev_metrics.model_params.accuracy as number).toFixed(1)}%`
                      : "N/A",
                  },
                  {
                    label: "ROI",
                    value: ev.metrics.data.ev_metrics.model_params.roi
                      ? `${(ev.metrics.data.ev_metrics.model_params.roi as number) > 0 ? "+" : ""}${(ev.metrics.data.ev_metrics.model_params.roi as number).toFixed(1)}%`
                      : "N/A",
                    color: (ev.metrics.data.ev_metrics.model_params.roi as number) > 0 ? "green" : "red",
                  },
                  {
                    label: "Games",
                    value: ev.metrics.data.ev_metrics.model_params.n_games ?? "N/A",
                  },
                ]}
              />

              {ev.metrics.data.ev_metrics.model_params.feature_importances && (
                <TmFeatureImportances
                  features={ev.metrics.data.ev_metrics.model_params.feature_importances}
                  title="EV Feature Importances"
                />
              )}

              {ev.metrics.data.ev_metrics.model_params.walk_forward && (
                <div className="card-surface rounded-sm p-4">
                  <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-2 uppercase">
                    Walk-Forward Results
                  </h4>
                  <TmStatCards
                    cards={[
                      {
                        label: "OOS Accuracy",
                        value: `${(ev.metrics.data.ev_metrics.model_params.walk_forward.oos_accuracy).toFixed(1)}%`,
                        color: ev.metrics.data.ev_metrics.model_params.walk_forward.oos_accuracy >= 53 ? "green" : "red",
                      },
                      {
                        label: "OOS ROI",
                        value: `${ev.metrics.data.ev_metrics.model_params.walk_forward.oos_roi > 0 ? "+" : ""}${ev.metrics.data.ev_metrics.model_params.walk_forward.oos_roi.toFixed(1)}%`,
                        color: ev.metrics.data.ev_metrics.model_params.walk_forward.oos_roi > 0 ? "green" : "red",
                      },
                      {
                        label: "OOS N",
                        value: ev.metrics.data.ev_metrics.model_params.walk_forward.oos_n,
                      },
                      {
                        label: "95% CI",
                        value: `${ev.metrics.data.ev_metrics.model_params.walk_forward.ci_lower.toFixed(1)}–${ev.metrics.data.ev_metrics.model_params.walk_forward.ci_upper.toFixed(1)}%`,
                      },
                    ]}
                  />
                </div>
              )}
            </div>
          )}

          {ev.metrics.data && (
            <div className="flex items-center gap-2 text-xs">
              <span className="font-heading tracking-wider text-muted-foreground">Model Status:</span>
              <span className={`font-mono ${ev.metrics.data.model_active ? "text-green-400" : "text-yellow-400"}`}>
                {ev.metrics.data.model_active ? "ACTIVE" : "INACTIVE"}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
