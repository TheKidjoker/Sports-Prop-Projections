import { useState } from "react";
import { useGames } from "@/hooks/use-games";
import type { GameListEntry, SportLower } from "@/lib/types";

interface TickerGame {
  id: string;
  away: string;
  home: string;
  time: string;
  dateLabel: string;
}

function mapToTicker(games: GameListEntry[]): TickerGame[] {
  return games.map((g) => ({
    id: g.event_id,
    away: g.away_team,
    home: g.home_team,
    time: g.game_time_est,
    dateLabel: g.date_label || "",
  }));
}

function GameItem({ game }: { game: TickerGame }) {
  return (
    <span className="inline-flex items-center gap-2 px-5 whitespace-nowrap">
      <span className="font-mono text-xs text-foreground">
        {game.away} <span className="text-muted-foreground">@</span> {game.home}
      </span>
      <span className="text-[10px] text-muted-foreground font-mono">
        {game.dateLabel ? `${game.dateLabel} — ` : ""}{game.time} EST
      </span>
    </span>
  );
}

export function GameTicker() {
  const [paused, setPaused] = useState(false);

  // Fetch games for active sports
  const nhl = useGames("nhl" as SportLower);
  const nba = useGames("nba" as SportLower);
  const cbb = useGames("cbb" as SportLower);

  const allGames: TickerGame[] = [
    ...mapToTicker(nhl.data?.games ?? []),
    ...mapToTicker(nba.data?.games ?? []),
    ...mapToTicker(cbb.data?.games ?? []),
  ];

  if (allGames.length === 0) {
    return (
      <div className="h-8 border-b border-border bg-muted/30 overflow-hidden relative">
        <div className="flex items-center h-full px-4">
          <span className="text-[10px] text-muted-foreground font-mono">
            {nhl.isLoading || nba.isLoading || cbb.isLoading
              ? "Loading games..."
              : "No games scheduled"}
          </span>
        </div>
      </div>
    );
  }

  // Duplicate for seamless loop
  const doubled = [...allGames, ...allGames];
  // Dynamic duration: ~8s per game, minimum 80s
  const duration = Math.max(80, allGames.length * 8);

  return (
    <div
      className="h-8 border-b border-border bg-muted/30 overflow-hidden relative"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div
        className="flex items-center h-full animate-ticker-scroll"
        style={{
          width: "fit-content",
          animationDuration: `${duration}s`,
          animationPlayState: paused ? "paused" : "running",
        }}
      >
        {doubled.map((game, i) => (
          <GameItem key={`${game.id}-${i}`} game={game} />
        ))}
      </div>
    </div>
  );
}
