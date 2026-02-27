import { motion } from "framer-motion";

interface TickerGame {
  id: string;
  away: string;
  home: string;
  awayScore?: number;
  homeScore?: number;
  spread: string;
  status: "live" | "final" | "upcoming";
  pick?: { team: string; result?: "HIT" | "MISS" };
}

const MOCK_TICKER: TickerGame[] = [
  { id: "1", away: "BOS", home: "NYR", awayScore: 3, homeScore: 2, spread: "NYR -135", status: "live", pick: { team: "BOS", result: "HIT" } },
  { id: "2", away: "LAL", home: "BOS", spread: "BOS -6.5", status: "upcoming" },
  { id: "3", away: "DET", home: "TBL", awayScore: 1, homeScore: 4, spread: "TBL -180", status: "final", pick: { team: "TBL", result: "HIT" } },
  { id: "4", away: "CHI", home: "MIL", spread: "MIL -8.5", status: "upcoming" },
  { id: "5", away: "PHX", home: "DEN", awayScore: 98, homeScore: 102, spread: "DEN -4.5", status: "live" },
  { id: "6", away: "CGY", home: "EDM", spread: "EDM -150", status: "upcoming", pick: { team: "EDM" } },
  { id: "7", away: "MIN", home: "DAL", awayScore: 3, homeScore: 1, spread: "MIN +120", status: "final", pick: { team: "MIN", result: "HIT" } },
  { id: "8", away: "WSH", home: "PIT", spread: "PIT -125", status: "upcoming" },
];

function GameItem({ game }: { game: TickerGame }) {
  return (
    <div className="flex items-center gap-3 px-4 py-1 border-r border-border whitespace-nowrap">
      <div className="flex items-center gap-2">
        {game.status === "live" && (
          <span className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse-dot" />
        )}
        <span className="font-mono text-xs text-foreground">
          {game.away}
          {game.awayScore !== undefined && (
            <span className="text-muted-foreground ml-1">{game.awayScore}</span>
          )}
        </span>
        <span className="text-muted-foreground text-xs">@</span>
        <span className="font-mono text-xs text-foreground">
          {game.home}
          {game.homeScore !== undefined && (
            <span className="text-muted-foreground ml-1">{game.homeScore}</span>
          )}
        </span>
      </div>
      <span className="text-[10px] text-muted-foreground font-mono">{game.spread}</span>
      {game.pick && (
        <span
          className={`text-[10px] font-heading px-1.5 py-0.5 rounded-sm ${
            game.pick.result === "HIT"
              ? "bg-success/20 text-success"
              : game.pick.result === "MISS"
              ? "bg-primary/20 text-primary"
              : "bg-secondary/20 text-secondary"
          }`}
        >
          {game.pick.result ?? "PICK"}
        </span>
      )}
      {game.status === "final" && (
        <span className="text-[10px] text-muted-foreground">FINAL</span>
      )}
    </div>
  );
}

export function GameTicker() {
  const doubled = [...MOCK_TICKER, ...MOCK_TICKER];

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
