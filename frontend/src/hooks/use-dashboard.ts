import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchDashboard, gradePredictions } from "@/lib/api";
import type { SportLower } from "@/lib/types";

export function useDashboard(sport?: SportLower) {
  return useQuery({
    queryKey: ["dashboard", sport ?? "all"],
    queryFn: () => fetchDashboard(sport),
  });
}

export function useGradePredictions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sport?: SportLower) => gradePredictions(sport),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
