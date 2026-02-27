interface StatsCardsProps {
  total: number;
  accuracy: number;
  pending: number;
  hits: number;
  misses: number;
  pushes: number;
}

export function StatsCards({ total, accuracy, pending, hits, misses, pushes }: StatsCardsProps) {
  const cards = [
    { label: "Total Picks", value: total, color: "text-foreground" },
    { label: "Win Rate", value: `${accuracy.toFixed(1)}%`, color: accuracy >= 55 ? "text-success" : "text-primary" },
    { label: "Pending", value: pending, color: "text-warning" },
    { label: "W / L / P", value: `${hits} / ${misses} / ${pushes}`, color: "text-foreground" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      {cards.map((card) => (
        <div key={card.label} className="card-surface rounded-sm p-4">
          <p className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1">
            {card.label}
          </p>
          <p className={`font-mono text-xl ${card.color}`}>{card.value}</p>
        </div>
      ))}
    </div>
  );
}
