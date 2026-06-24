import { HudPanel } from "@/components/jarvis/HudPanel";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { SPORTS } from "@/components/navigation/SportPills";
import type { Sport } from "@/lib/types";

interface SportCommandCardsProps {
  gameCounts: Record<string, number>;
  onSelectSport: (sport: Sport) => void;
}

const sportColors: Record<string, string> = {
  NHL: "hsl(200, 70%, 50%)",
  NBA: "hsl(43, 76%, 38%)",
  MLB: "hsl(0, 72%, 51%)",
  NFL: "hsl(142, 71%, 45%)",
  CFB: "hsl(280, 60%, 55%)",
  CBB: "hsl(30, 80%, 50%)",
  SOCCER: "hsl(120, 50%, 40%)",
};

export function SportCommandCards({ gameCounts, onSelectSport }: SportCommandCardsProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
      {SPORTS.map((sport) => {
        const count = gameCounts[sport.id] ?? 0;
        const hasGames = count > 0;
        return (
          <button key={sport.id} onClick={() => onSelectSport(sport.id)} className="text-left">
            <HudPanel
              title={sport.label}
              status={hasGames ? "online" : "offline"}
              glow={hasGames}
              className="hover:translate-y-[-2px] transition-transform duration-200 cursor-pointer"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-lg text-foreground">{count}</span>
                <HexBadge label={sport.label} color={sportColors[sport.id]} size="sm" active={hasGames} />
              </div>
              <p className="text-[12px] text-muted-foreground font-heading tracking-wider mt-1">
                {hasGames ? "GAMES TODAY" : "NO GAMES"}
              </p>
            </HudPanel>
          </button>
        );
      })}
    </div>
  );
}
