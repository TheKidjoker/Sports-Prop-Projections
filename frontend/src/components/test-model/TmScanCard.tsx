import type { TmScanGame } from "@/lib/types";

interface TmScanCardProps {
  game: TmScanGame;
}

export function TmScanCard({ game }: TmScanCardProps) {
  const coverColor =
    game.cover_pct >= 65 ? "text-success" : game.cover_pct >= 55 ? "text-warning" : "text-primary";

  return (
    <div className="card-surface rounded-sm p-4">
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="font-heading text-sm tracking-wider text-foreground">
            {game.away_team} @ {game.home_team}
          </span>
          <span className="text-xs text-muted-foreground ml-2">{game.game_time_est}</span>
        </div>
        <span
          className={`text-xs font-heading tracking-wider px-2 py-0.5 rounded-sm ${
            game.recommendation === "STRONG PLAY"
              ? "bg-success/20 text-success"
              : game.recommendation === "LEAN"
              ? "bg-warning/20 text-warning"
              : "bg-muted text-muted-foreground"
          }`}
        >
          {game.recommendation}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <div>
          <span className="text-muted-foreground">Lean:</span>{" "}
          <span className="font-mono text-foreground">{game.lean_team}</span>
          {game.current_spread != null && (
            <span className="font-mono text-muted-foreground ml-1">
              ({game.current_spread > 0 ? "+" : ""}{game.current_spread})
            </span>
          )}
        </div>
        <div>
          <span className="text-muted-foreground">Score:</span>{" "}
          <span className="font-mono text-foreground">{game.confirmation_score}</span>
        </div>
        <div>
          <span className="text-muted-foreground">Cover:</span>{" "}
          <span className={`font-mono ${coverColor}`}>{game.cover_pct.toFixed(1)}%</span>
        </div>
        <div>
          <span className="text-muted-foreground">Slot:</span>{" "}
          <span className="font-mono text-foreground">{game.slot_type ?? "—"}</span>
        </div>
      </div>

      {game.ml_overlay && (
        <div className="mt-2 pt-2 border-t border-border grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
          {game.ml_overlay.model_prob != null && (
            <div>
              <span className="text-muted-foreground">ML Prob:</span>{" "}
              <span className="font-mono text-foreground">
                {(game.ml_overlay.model_prob * 100).toFixed(1)}%
              </span>
            </div>
          )}
          {game.ml_overlay.edge != null && (
            <div>
              <span className="text-muted-foreground">Edge:</span>{" "}
              <span
                className={`font-mono ${
                  game.ml_overlay.edge > 0 ? "text-success" : "text-primary"
                }`}
              >
                {game.ml_overlay.edge > 0 ? "+" : ""}
                {(game.ml_overlay.edge * 100).toFixed(1)}%
              </span>
            </div>
          )}
          {game.ml_overlay.ev != null && (
            <div>
              <span className="text-muted-foreground">EV:</span>{" "}
              <span
                className={`font-mono ${
                  game.ml_overlay.ev > 0 ? "text-success" : "text-primary"
                }`}
              >
                {game.ml_overlay.ev > 0 ? "+" : ""}
                {game.ml_overlay.ev.toFixed(2)}
              </span>
            </div>
          )}
          {game.ml_overlay.cluster && (
            <div>
              <span className="text-muted-foreground">Cluster:</span>{" "}
              <span className="font-mono text-foreground">{game.ml_overlay.cluster}</span>
            </div>
          )}
          {game.ml_overlay.sentiment && (
            <div>
              <span className="text-muted-foreground">Sentiment:</span>{" "}
              <span className="font-mono text-foreground">{game.ml_overlay.sentiment}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
