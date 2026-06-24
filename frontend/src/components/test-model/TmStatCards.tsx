interface StatCard {
  label: string;
  value: string | number;
  color?: "default" | "green" | "red" | "yellow";
}

interface TmStatCardsProps {
  cards: StatCard[];
}

const colorMap = {
  default: "text-foreground",
  green: "text-green-400",
  red: "text-red-400",
  yellow: "text-yellow-400",
};

export function TmStatCards({ cards }: TmStatCardsProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {cards.map((card) => (
        <div key={card.label} className="card-surface rounded-sm p-3">
          <p className="text-[13px] text-muted-foreground font-heading tracking-wider uppercase">
            {card.label}
          </p>
          <p className={`text-lg font-mono font-bold ${colorMap[card.color ?? "default"]}`}>
            {card.value}
          </p>
        </div>
      ))}
    </div>
  );
}
