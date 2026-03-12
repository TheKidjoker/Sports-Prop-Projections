import { useMutation, useQueries } from "@tanstack/react-query";
import { scanAllSports, fetchTopProps } from "@/lib/api";
import {
  scanGameToPickData,
  type PickData,
  type PropSignal,
  type SportLower,
  type ScanAllResponse,
} from "@/lib/types";

const PROP_SPORTS: SportLower[] = ["nba", "nhl", "cbb"];

export function useParlays() {
  const scanMutation = useMutation({
    mutationFn: scanAllSports,
  });

  // Derive picks from scan response
  const allPicks: PickData[] = [];
  if (scanMutation.data?.all_sports) {
    const sportGames = scanMutation.data.all_sports as ScanAllResponse["all_sports"];
    for (const [sport, games] of Object.entries(sportGames)) {
      for (const game of games) {
        allPicks.push(scanGameToPickData(game, sport as SportLower));
      }
    }
  }

  // Fetch props for NBA and NHL in parallel (only after scan completes)
  const propQueries = useQueries({
    queries: PROP_SPORTS.map((sport) => ({
      queryKey: ["top-props", sport],
      queryFn: () => fetchTopProps(sport),
      enabled: scanMutation.isSuccess,
      staleTime: 5 * 60 * 1000,
    })),
  });

  // Merge props from all sport queries, tagging each with its sport
  const allProps: (PropSignal & { _sport: SportLower })[] = [];
  propQueries.forEach((q, i) => {
    if (q.data?.props) {
      for (const prop of q.data.props) {
        allProps.push({ ...prop, _sport: PROP_SPORTS[i] });
      }
    }
  });

  const propsComplete = propQueries.filter((q) => q.isSuccess).length;
  const propsTotal = PROP_SPORTS.length;
  const propsLoading = propQueries.some((q) => q.isLoading);

  return {
    triggerScan: scanMutation.mutate,
    scanLoading: scanMutation.isPending,
    scanError: scanMutation.error,
    allPicks,
    allProps,
    propsLoading,
    propsComplete,
    propsTotal,
  };
}
