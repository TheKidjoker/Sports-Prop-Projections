import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scanSport } from "@/lib/api";
import { scanGameToPickData, type PickData, type SportLower } from "@/lib/types";

export function useScan(sport: SportLower) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => scanSport(sport),
    onSuccess: (data) => {
      queryClient.setQueryData(["scan", sport], data);
      // Seed props cache from scan response (avoids separate fetch)
      if (data.props) {
        queryClient.setQueryData(["top-props", sport], { success: true, props: data.props });
      }
    },
  });

  const picks: PickData[] = (mutation.data?.games ?? []).map((g) =>
    scanGameToPickData(g, sport)
  );

  return {
    scan: mutation.mutate,
    isScanning: mutation.isPending,
    picks,
    rawGames: mutation.data?.games ?? [],
    pendingReview: mutation.data?.picks_pending_review ?? false,
    cached: mutation.data?.cached ?? false,
    error: mutation.error,
  };
}
