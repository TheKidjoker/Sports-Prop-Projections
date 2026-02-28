import { useTmScan } from "@/hooks/use-test-model";
import { TmScanCard } from "./TmScanCard";
import type { SportLower } from "@/lib/types";

interface ScanPanelProps {
  sport: SportLower;
}

export function ScanPanel({ sport }: ScanPanelProps) {
  const scan = useTmScan(sport);
  const games = scan.data?.games ?? [];

  return (
    <div className="space-y-4">
      <button
        onClick={() => scan.mutate()}
        disabled={scan.isPending}
        className="px-4 py-2 bg-primary text-primary-foreground font-heading tracking-[0.12em] text-xs rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
      >
        {scan.isPending ? "SCANNING..." : "RUN MODEL SCAN"}
      </button>

      {scan.error && (
        <p className="text-xs text-red-400 font-mono">
          Error: {(scan.error as Error).message}
        </p>
      )}

      {games.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground font-heading tracking-wider">
            {games.length} game{games.length !== 1 ? "s" : ""} scanned
          </p>
          {games.map((g) => (
            <TmScanCard key={g.event_id} game={g} />
          ))}
        </div>
      )}

      {scan.isSuccess && games.length === 0 && (
        <p className="text-xs text-muted-foreground font-mono">
          No games found for {sport.toUpperCase()}.
        </p>
      )}
    </div>
  );
}
