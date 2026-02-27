import { motion } from "framer-motion";
import { SPORTS } from "../navigation/SportPills";
import { ArrowRight } from "lucide-react";
import { useAllGameCounts } from "@/hooks/use-games";
import type { Sport } from "@/lib/types";

const confidenceBadge = {
  validated: { label: "VALIDATED", className: "bg-success/15 text-success border-success/30" },
  experimental: { label: "EXPERIMENTAL", className: "bg-warning/15 text-warning border-warning/30" },
  limited: { label: "LIMITED DATA", className: "bg-primary/15 text-primary border-primary/30" },
};

interface HeroSectionProps {
  onSelectSport: (sport: Sport) => void;
  onScan: () => void;
  selectedSport: Sport | null;
}

export function HeroSection({ onSelectSport, onScan, selectedSport }: HeroSectionProps) {
  const gameCounts = useAllGameCounts();

  return (
    <div className="py-16 px-6">
      {/* Tagline */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center mb-12"
      >
        <h2 className="text-5xl md:text-7xl font-heading tracking-[0.1em] text-foreground mb-3">
          WHY SO <span className="text-primary">SERIOUS</span>?
        </h2>
        <p className="text-muted-foreground text-sm tracking-wider font-heading">
          THE EDGE THEY DON'T WANT YOU TO HAVE
        </p>
      </motion.div>

      {/* Sport Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 max-w-5xl mx-auto mb-10">
        {SPORTS.map((sport, i) => {
          const badge = confidenceBadge[sport.confidence];
          const isSelected = selectedSport === sport.id;
          const count = gameCounts[sport.id] ?? 0;
          return (
            <motion.button
              key={sport.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.08, duration: 0.4 }}
              onClick={() => onSelectSport(sport.id)}
              className={`card-surface p-4 text-left transition-all duration-200 rounded-sm group hover:glow-crimson ${
                isSelected ? "border-primary glow-crimson" : ""
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <span className="font-heading text-2xl tracking-wider text-foreground">
                  {sport.label}
                </span>
                <span
                  className={`text-[9px] font-heading px-1.5 py-0.5 border rounded-sm ${badge.className}`}
                >
                  {badge.label}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mb-2 font-heading tracking-wider">
                {sport.subtitle}
              </p>
              <p className="font-mono text-xs text-foreground">
                {count > 0 ? (
                  <>
                    <span className="text-primary font-semibold">{count}</span> games today
                  </>
                ) : (
                  <span className="text-muted-foreground">No games today</span>
                )}
              </p>
            </motion.button>
          );
        })}
      </div>

      {/* CTA */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="text-center"
      >
        <button
          onClick={onScan}
          className="inline-flex items-center gap-2 px-8 py-3 bg-primary text-primary-foreground font-heading tracking-[0.15em] text-sm rounded-sm transition-all duration-200 hover:glow-crimson hover:bg-primary/90 active:scale-[0.98]"
        >
          GET PICKS
          <ArrowRight className="w-4 h-4" />
        </button>
        {!selectedSport && (
          <p className="text-muted-foreground text-xs mt-3 font-heading tracking-wider">
            SELECT A SPORT ABOVE TO BEGIN
          </p>
        )}
      </motion.div>
    </div>
  );
}
