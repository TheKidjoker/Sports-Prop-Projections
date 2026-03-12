import { motion, useReducedMotion } from "framer-motion";
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
  const prefersReducedMotion = useReducedMotion();

  return (
    <div className="py-8 sm:py-16 px-3 sm:px-6">
      {/* Logo + Tagline */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="text-center mb-8 sm:mb-12"
      >
        <motion.img
          src="/static/logo.png"
          alt="Joker's Edge"
          className="w-32 h-32 sm:w-44 sm:h-44 md:w-56 md:h-56 mx-auto mb-4 sm:mb-6 drop-shadow-[0_0_25px_rgba(220,38,38,0.3)]"
          animate={prefersReducedMotion ? {} : { rotate: [0, 2, -2, 0] }}
          transition={prefersReducedMotion ? {} : { duration: 6, repeat: Infinity, ease: "easeInOut" }}
        />
        <h2 className="text-3xl sm:text-5xl md:text-7xl font-heading tracking-[0.1em] text-foreground mb-2 sm:mb-3">
          WHY SO <span className="text-primary">SERIOUS</span>?
        </h2>
        <p className="text-muted-foreground text-xs sm:text-sm tracking-wider font-heading">
          THE EDGE THEY DON'T WANT YOU TO HAVE
        </p>
      </motion.div>

      {/* Sport Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 sm:gap-3 max-w-5xl mx-auto mb-8 sm:mb-10">
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
              className={`card-surface p-3 sm:p-4 text-left transition-all duration-200 rounded-sm group hover:glow-crimson ${
                isSelected ? "border-primary glow-crimson" : ""
              }`}
            >
              <div className="flex items-start justify-between mb-2 sm:mb-3">
                <span className="font-heading text-xl sm:text-2xl tracking-wider text-foreground">
                  {sport.label}
                </span>
                <span
                  className={`text-[8px] sm:text-[9px] font-heading px-1 sm:px-1.5 py-0.5 border rounded-sm ${badge.className}`}
                >
                  {badge.label}
                </span>
              </div>
              <p className="text-[10px] sm:text-xs text-muted-foreground mb-1.5 sm:mb-2 font-heading tracking-wider">
                {sport.subtitle}
              </p>
              <p className="font-mono text-[10px] sm:text-xs text-foreground">
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
