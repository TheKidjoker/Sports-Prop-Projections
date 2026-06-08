import { useQuery, useQueries } from "@tanstack/react-query";
import { fetchGames } from "@/lib/api";
import type { SportLower, GamesResponse } from "@/lib/types";

export function useGames(sport: SportLower) {
  return useQuery({
    queryKey: ["games", sport],
    queryFn: () => fetchGames(sport),
    refetchInterval: 3 * 60 * 1000, // 3 min (matches old version)
  });
}

const ALL_SPORTS: SportLower[] = ["nhl", "nba", "mlb", "nfl", "cfb", "cbb"];

export function useAllGameCounts() {
  const results = useQueries({
    queries: ALL_SPORTS.map((sport) => ({
      queryKey: ["games", sport],
      queryFn: () => fetchGames(sport),
      refetchInterval: 5 * 60 * 1000,
    })),
  });

  const counts: Record<string, number> = {};
  results.forEach((result, i) => {
    const data = result.data as GamesResponse | undefined;
    counts[ALL_SPORTS[i].toUpperCase()] = data?.slate?.game_count ?? 0;
  });

  return counts;
}
