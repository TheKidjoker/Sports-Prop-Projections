import { useMutation, useQueryClient } from "@tanstack/react-query";
import { scanSport, scanSoccerLeague } from "@/lib/api";
import { scanGameToPickData, type PickData, type SportLower, type ScanResponse } from "@/lib/types";

export function useScan(sport: SportLower) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (): Promise<ScanResponse> => {
      if (sport === "soccer") {
        // Soccer uses a different endpoint; scan EPL as default league
        const res = await scanSoccerLeague("epl");
        return {
          success: res.success,
          games: res.matches ?? [],
        };
      }
      return scanSport(sport);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["scan", sport], data);
      // Seed props cache from scan response (avoids separate fetch)
      if ((data as Record<string, unknown>).props) {
        queryClient.setQueryData(["top-props", sport], { success: true, props: (data as Record<string, unknown>).props });
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
