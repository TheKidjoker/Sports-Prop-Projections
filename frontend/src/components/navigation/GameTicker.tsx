import { motion } from "framer-motion";
import { useGames } from "@/hooks/use-games";
import type { GameListEntry, SportLower } from "@/lib/types";

interface TickerGame {
  id: string;
  away: string;
  home: string;
  spread: string;
  status: "upcoming";
  time: string;
}

function mapToTicker(games: GameListEntry[]): TickerGame[] {
  return games.map((g) => ({
    id: g.event_id,
    away: g.away_team,
    home: g.home_team,
    spread: "",
    status: "upcoming" as const,
    time: g.game_time_est,
  }));
}

function GameItem({ game }: { game: TickerGame }) {
  return (
    <div className="flex items-center gap-3 px-4 py-1 border-r border-border whitespace-nowrap">
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs text-foreground">{game.away}</span>
        <span className="text-muted-foreground text-xs">@</span>
        <span className="font-mono text-xs text-foreground">{game.home}</span>
      </div>
      <span className="text-[10px] text-muted-foreground font-mono">{game.time}</span>
    </div>
  );
}

export function GameTicker() {
  // Fetch games for active sports
  const nhl = useGames("nhl" as SportLower);
  const nba = useGames("nba" as SportLower);
  const cbb = useGames("cbb" as SportLower);

  const allGames: TickerGame[] = [
    ...mapToTicker(nhl.data?.games ?? []),
    ...mapToTicker(nba.data?.games ?? []),
    ...mapToTicker(cbb.data?.games ?? []),
  ];

  // Need at least a few items for the scroll to look right
  if (allGames.length === 0) {
    return (
      <div className="h-8 border-b border-border bg-muted/30 overflow-hidden relative">
        <div className="flex items-center h-full px-4">
          <span className="text-[10px] text-muted-foreground font-mono">
            Loading games...
          </span>
        </div>
      </div>
    );
  }

  const doubled = [...allGames, ...allGames];

  return (
    <div className="h-8 border-b border-border bg-muted/30 overflow-hidden relative">
      <motion.div
        className="flex items-center h-full animate-ticker-scroll"
        style={{ width: "fit-content" }}
      >
        {doubled.map((game, i) => (
          <GameItem key={`${game.id}-${i}`} game={game} />
        ))}
      </motion.div>
    </div>
  );
}
