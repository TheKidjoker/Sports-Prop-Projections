import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchBets, saveBets, gradeBets, fetchBetsDashboard, deleteBet } from "@/lib/api";
import type { SportLower } from "@/lib/types";

export function useTrackedBets(sport?: SportLower, status?: string) {
  return useQuery({
    queryKey: ["bets", sport ?? "all", status ?? "all"],
    queryFn: () => fetchBets(sport, status),
  });
}

export function useSaveBets() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bets: unknown[]) => saveBets(bets),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bets"] });
      queryClient.invalidateQueries({ queryKey: ["bets-dashboard"] });
    },
  });
}

export function useGradeBets() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => gradeBets(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bets"] });
      queryClient.invalidateQueries({ queryKey: ["bets-dashboard"] });
    },
  });
}

export function useDeleteBet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (betId: number) => deleteBet(betId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bets"] });
      queryClient.invalidateQueries({ queryKey: ["bets-dashboard"] });
    },
  });
}

export function useBetsDashboard(sport?: SportLower) {
  return useQuery({
    queryKey: ["bets-dashboard", sport ?? "all"],
    queryFn: () => fetchBetsDashboard(sport),
  });
}
