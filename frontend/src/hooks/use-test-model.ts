import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  tmStartCollect,
  tmCollectStatus,
  tmComputeFeatures,
  tmStartBacktest,
  tmBacktestStatus,
  tmScanToday,
  tmFetchMetrics,
  tmStartRulesBacktest,
  tmRulesBacktestStatus,
  tmFetchRulesMetrics,
  tmFetchCalibration,
  tmStartEvTrain,
  tmEvStatus,
  tmEvMetrics,
} from "@/lib/api";
import type { SportLower } from "@/lib/types";

const POLL_MS = 5000;

function isRunning(status?: string) {
  return status === "running";
}

// ─── Data Collection ──────────────────────────────────
export function useTmCollect(sport: SportLower) {
  const qc = useQueryClient();

  const start = useMutation({
    mutationFn: () => tmStartCollect(sport),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tm-collect-status", sport] }),
  });

  const status = useQuery({
    queryKey: ["tm-collect-status", sport],
    queryFn: () => tmCollectStatus(sport),
    refetchInterval: (query) =>
      isRunning(query.state.data?.progress?.status) ? POLL_MS : false,
    enabled: start.isSuccess || start.isPending,
  });

  const features = useMutation({
    mutationFn: () => tmComputeFeatures(sport),
  });

  return { start, status, features };
}

// ─── Walk-Forward Backtest ────────────────────────────
export function useTmBacktest(sport: SportLower) {
  const qc = useQueryClient();

  const start = useMutation({
    mutationFn: () => tmStartBacktest(sport),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tm-backtest-status", sport] }),
  });

  const status = useQuery({
    queryKey: ["tm-backtest-status", sport],
    queryFn: () => tmBacktestStatus(sport),
    refetchInterval: (query) =>
      isRunning(query.state.data?.progress?.status) ? POLL_MS : false,
    enabled: start.isSuccess || start.isPending,
  });

  return { start, status };
}

// ─── Rules Replay ─────────────────────────────────────
export function useTmRulesReplay(sport: SportLower) {
  const qc = useQueryClient();

  const start = useMutation({
    mutationFn: () => tmStartRulesBacktest(sport),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tm-rules-status", sport] }),
  });

  const status = useQuery({
    queryKey: ["tm-rules-status", sport],
    queryFn: () => tmRulesBacktestStatus(sport),
    refetchInterval: (query) =>
      isRunning(query.state.data?.progress?.status) ? POLL_MS : false,
    enabled: start.isSuccess || start.isPending,
  });

  const metrics = useQuery({
    queryKey: ["tm-rules-metrics", sport],
    queryFn: () => tmFetchRulesMetrics(sport),
    enabled: false,
  });

  return { start, status, metrics };
}

// ─── Model Scan ───────────────────────────────────────
export function useTmScan(sport: SportLower) {
  const scan = useMutation({
    mutationFn: () => tmScanToday(sport),
  });
  return scan;
}

// ─── Calibration ──────────────────────────────────────
export function useTmCalibration(sport: SportLower) {
  return useQuery({
    queryKey: ["tm-calibration", sport],
    queryFn: () => tmFetchCalibration(sport),
    enabled: false,
  });
}

// ─── Metrics ──────────────────────────────────────────
export function useTmMetrics(sport: SportLower) {
  return useQuery({
    queryKey: ["tm-metrics", sport],
    queryFn: () => tmFetchMetrics(sport),
  });
}

// ─── EV Model ─────────────────────────────────────────
export function useTmEvTrain(sport: SportLower) {
  const qc = useQueryClient();

  const start = useMutation({
    mutationFn: () => tmStartEvTrain(sport),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tm-ev-status", sport] }),
  });

  const status = useQuery({
    queryKey: ["tm-ev-status", sport],
    queryFn: () => tmEvStatus(sport),
    refetchInterval: (query) =>
      isRunning(query.state.data?.progress?.status) ? POLL_MS : false,
    enabled: start.isSuccess || start.isPending,
  });

  const metrics = useQuery({
    queryKey: ["tm-ev-metrics", sport],
    queryFn: () => tmEvMetrics(sport),
    enabled: false,
  });

  return { start, status, metrics };
}
