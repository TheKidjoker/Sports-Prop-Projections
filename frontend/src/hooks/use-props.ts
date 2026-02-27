import { useQuery } from "@tanstack/react-query";
import { fetchProps, fetchTopProps } from "@/lib/api";
import type { SportLower } from "@/lib/types";

export function useGameProps(eventId: string, sport: SportLower) {
  return useQuery({
    queryKey: ["props", eventId, sport],
    queryFn: () => fetchProps(eventId, sport),
    enabled: false, // on-demand via refetch
  });
}

export function useTopProps(sport: SportLower, enabled: boolean) {
  return useQuery({
    queryKey: ["top-props", sport],
    queryFn: () => fetchTopProps(sport),
    enabled,
  });
}
