import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchPendingPicks, approvePick, rejectPick, approveAllPicks } from "@/lib/api";
import type { SportLower } from "@/lib/types";

export function usePendingPicks(sport: SportLower) {
  return useQuery({
    queryKey: ["pending-picks", sport],
    queryFn: () => fetchPendingPicks(sport),
  });
}

export function useApprovePick() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ eventId, sport }: { eventId: string; sport: SportLower }) =>
      approvePick(eventId, sport),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending-picks"] });
    },
  });
}

export function useRejectPick() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ eventId, sport }: { eventId: string; sport: SportLower }) =>
      rejectPick(eventId, sport),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending-picks"] });
    },
  });
}

export function useApproveAll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sport: SportLower) => approveAllPicks(sport),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pending-picks"] });
    },
  });
}
