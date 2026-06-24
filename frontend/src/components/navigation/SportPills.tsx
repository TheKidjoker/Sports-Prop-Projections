import { HexBadge } from "@/components/jarvis/HexBadge";
import type { Sport } from "@/lib/types";

export type { Sport };

export interface SportConfig {
  id: Sport;
  label: string;
  subtitle: string;
  confidence: "validated" | "experimental" | "limited";
  confidenceLabel: string;
  gamesCount: number;
}

export const SPORTS: SportConfig[] = [
  { id: "NHL", label: "NHL", subtitle: "Gotham Ice", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
  { id: "NBA", label: "NBA", subtitle: "Gotham Court", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
  { id: "MLB", label: "MLB", subtitle: "Gotham Diamond", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
  { id: "NFL", label: "NFL", subtitle: "Gotham Gridiron", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
  { id: "CFB", label: "CFB", subtitle: "Gotham College", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
  { id: "CBB", label: "CBB", subtitle: "Gotham Hardwood", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
  { id: "SOCCER", label: "SOCCER", subtitle: "Gotham Pitch", confidence: "experimental", confidenceLabel: "Experimental", gamesCount: 0 },
];

const sportColors: Record<string, string> = {
  NHL: "hsl(200, 70%, 50%)",
  NBA: "hsl(43, 76%, 38%)",
  MLB: "hsl(0, 72%, 51%)",
  NFL: "hsl(142, 71%, 45%)",
  CFB: "hsl(280, 60%, 55%)",
  CBB: "hsl(30, 80%, 50%)",
  SOCCER: "hsl(120, 50%, 40%)",
};

interface SportPillsProps {
  selected: Sport | null;
  onSelect: (sport: Sport | null) => void;
  gameCounts?: Record<string, number>;
}

export function SportPills({ selected, onSelect, gameCounts }: SportPillsProps) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      <HexBadge
        label="ALL"
        size="md"
        active={selected === null}
        color="hsl(0, 72%, 51%)"
        onClick={() => onSelect(null)}
      />
      {SPORTS.map((sport) => {
        const count = gameCounts?.[sport.id] ?? sport.gamesCount;
        return (
          <div key={sport.id} className="relative">
            <HexBadge
              label={sport.label}
              size="md"
              active={selected === sport.id}
              color={sportColors[sport.id] ?? "hsl(0, 72%, 51%)"}
              onClick={() => onSelect(sport.id === selected ? null : sport.id)}
            />
            {count > 0 && (
              <span className="absolute -top-1 -right-1 text-[10px] font-mono text-foreground bg-muted border border-border rounded-full w-3.5 h-3.5 flex items-center justify-center">
                {count}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
