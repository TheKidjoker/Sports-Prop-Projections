import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { PickCard } from "./PickCard";
import { PickCardSkeleton } from "./PickCardSkeleton";
import { MOCK_PICKS } from "./mockPicks";
import type { Sport } from "../navigation/SportPills";

interface ScanResultsProps {
  sport: Sport;
  isAdmin?: boolean;
}

export function ScanResults({ sport, isAdmin }: ScanResultsProps) {
  const [loading, setLoading] = useState(true);
  const [picks, setPicks] = useState(MOCK_PICKS);

  useEffect(() => {
    setLoading(true);
    const timer = setTimeout(() => {
      setPicks(MOCK_PICKS);
      setLoading(false);
    }, 1500);
    return () => clearTimeout(timer);
  }, [sport]);

  const topPicks = picks.filter((p) => p.coverPct >= 68.5);
  const watchPicks = picks.filter((p) => p.coverPct >= 58 && p.coverPct < 68.5);

  return (
    <div className="py-6 px-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <h2 className="font-heading text-xl tracking-wider text-foreground">
          {sport} <span className="text-primary">SCAN RESULTS</span>
        </h2>
        <span className="font-mono text-xs text-muted-foreground">
          {picks.length} games analyzed
        </span>
      </div>

      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <PickCardSkeleton key={i} />
          ))}
        </div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div key={sport} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {topPicks.length > 0 && (
              <div className="mb-8">
                <h3 className="font-heading text-xs tracking-[0.2em] text-primary mb-3">
                  TOP PICKS
                </h3>
                <div className="space-y-3">
                  {topPicks.map((pick, i) => (
                    <PickCard key={pick.id} pick={pick} index={i} isAdmin={isAdmin} />
                  ))}
                </div>
              </div>
            )}

            {watchPicks.length > 0 && (
              <div>
                <h3 className="font-heading text-xs tracking-[0.2em] text-secondary mb-3">
                  OTHER GAMES TO WATCH
                </h3>
                <div className="space-y-3">
                  {watchPicks.map((pick, i) => (
                    <PickCard key={pick.id} pick={pick} index={i + topPicks.length} isAdmin={isAdmin} />
                  ))}
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}
