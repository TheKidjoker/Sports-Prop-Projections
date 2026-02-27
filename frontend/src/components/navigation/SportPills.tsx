import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { Sport } from "@/lib/types";

export type { Sport };

interface SportConfig {
  id: Sport;
  label: string;
  subtitle: string;
  confidence: "validated" | "experimental" | "limited";
  confidenceLabel: string;
  gamesCount: number;
}

export const SPORTS: SportConfig[] = [
  { id: "NHL", label: "NHL", subtitle: "Gotham Ice", confidence: "validated", confidenceLabel: "Validated Model", gamesCount: 0 },
  { id: "NBA", label: "NBA", subtitle: "Gotham Court", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
  { id: "NFL", label: "NFL", subtitle: "Gotham Gridiron", confidence: "limited", confidenceLabel: "Limited Data", gamesCount: 0 },
  { id: "CFB", label: "CFB", subtitle: "Gotham College", confidence: "limited", confidenceLabel: "Limited Data", gamesCount: 0 },
  { id: "CBB", label: "CBB", subtitle: "Gotham Hardwood", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
];

const confidenceDotColor = {
  validated: "bg-success",
  experimental: "bg-warning",
  limited: "bg-primary",
};

interface SportPillsProps {
  selected: Sport | null;
  onSelect: (sport: Sport | null) => void;
  gameCounts?: Record<string, number>;
}

export function SportPills({ selected, onSelect, gameCounts }: SportPillsProps) {
  const [hoveredSport, setHoveredSport] = useState<Sport | null>(null);

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => onSelect(null)}
        className={`px-3 py-1.5 text-xs font-heading tracking-wider transition-all duration-200 rounded-sm ${
          selected === null
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:text-foreground hover:bg-accent"
        }`}
      >
        ALL
      </button>
      {SPORTS.map((sport) => {
        const count = gameCounts?.[sport.id] ?? sport.gamesCount;
        return (
          <div
            key={sport.id}
            className="relative"
            onMouseEnter={() => setHoveredSport(sport.id)}
            onMouseLeave={() => setHoveredSport(null)}
          >
            <button
              onClick={() => onSelect(sport.id === selected ? null : sport.id)}
              className={`px-3 py-1.5 text-xs font-heading tracking-wider transition-all duration-200 rounded-sm flex items-center gap-1.5 ${
                selected === sport.id
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${confidenceDotColor[sport.confidence]} ${
                  sport.confidence === "limited" ? "" : "animate-pulse-dot"
                }`}
              />
              {sport.label}
              {count > 0 && (
                <span className="text-[9px] text-muted-foreground font-mono">
                  {count}
                </span>
              )}
            </button>

            <AnimatePresence>
              {hoveredSport === sport.id && (
                <motion.div
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 4 }}
                  className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-2 glass rounded-sm text-xs whitespace-nowrap z-50"
                >
                  <p className="text-foreground font-medium">{sport.subtitle}</p>
                  <p className="text-muted-foreground">{sport.confidenceLabel}</p>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}
