import { useState } from "react";
import { useGames } from "@/hooks/use-games";
import { HexBadge } from "@/components/jarvis/HexBadge";
import type { GameListEntry, SportLower } from "@/lib/types";

interface TickerGame {
  id: string;
  away: string;
  home: string;
  time: string;
  dateLabel: string;
  sport: string;
  isLive?: boolean;
}

const TICKER_SPORTS: SportLower[] = ["nhl", "nba", "mlb", "nfl", "cbb", "cfb"];

function mapToTicker(games: GameListEntry[], sport: string): TickerGame[] {
  return games.map((g) => ({
    id: g.event_id,
    away: g.away_team,
    home: g.home_team,
    time: g.game_time_est,
    dateLabel: g.date_label || "",
    sport: sport.toUpperCase(),
  }));
}

function GameItem({ game }: { game: TickerGame }) {
  return (
    <span className="inline-flex items-center gap-2 px-4 whitespace-nowrap">
      <HexBadge label={game.sport.slice(0, 3)} size="sm" active />
      <span className="font-mono-nums text-[11px] text-foreground">
        {game.away}
        <span className="text-muted-foreground mx-1">@</span>
        {game.home}
      </span>
      <span className="text-[9px] text-muted-foreground font-mono">
        {game.dateLabel ? `${game.dateLabel} ` : ""}{game.time}
      </span>
    </span>
  );
}

export function GameTicker() {
  const [paused, setPaused] = useState(false);

  const queries = TICKER_SPORTS.map((sport) => ({
    sport,
    ...useGames(sport),
  }));

  const allGames: TickerGame[] = queries.flatMap(
    (q) => mapToTicker(q.data?.games ?? [], q.sport)
  );

  const isLoading = queries.some((q) => q.isLoading);

  if (allGames.length === 0) {
    return (
      <div className="h-8 border-b border-border bg-muted/20 overflow-hidden relative hex-grid-bg">
        <div className="flex items-center h-full px-4">
          <span className="text-[10px] text-muted-foreground font-mono">
            {isLoading ? "LOADING OPERATIONS..." : "NO ACTIVE OPERATIONS"}
          </span>
        </div>
      </div>
    );
  }

  const doubled = [...allGames, ...allGames];
  const duration = Math.max(80, allGames.length * 8);

  return (
    <div
      className="h-8 border-b border-border bg-muted/20 overflow-hidden relative hex-grid-bg"
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
