import { Home, Zap, BookOpen, DollarSign, FlaskConical, User, Layers } from "lucide-react";

interface MobileNavProps {
  activeSection: string;
  onSelectSection: (id: string) => void;
}

const items = [
  { icon: Home, label: "Home", id: "home" },
  { icon: Zap, label: "Picks", id: "picks" },
  { icon: User, label: "Props", id: "props" },
  { icon: Layers, label: "Parlays", id: "parlays" },
  { icon: BookOpen, label: "Ledger", id: "ledger" },
  { icon: DollarSign, label: "Bets", id: "bets" },
  { icon: FlaskConical, label: "Test", id: "test" },
];

export function MobileNav({ activeSection, onSelectSection }: MobileNavProps) {
  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-40 glass border-t border-border pb-[env(safe-area-inset-bottom)]">
      <div className="flex items-center justify-around h-14">
        {items.map((item) => {
          const active = activeSection === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectSection(item.id)}
              className={`flex flex-col items-center gap-0.5 py-1 px-1.5 min-w-0 transition-colors ${
                active ? "text-primary" : "text-muted-foreground"
              }`}
            >
              <item.icon className="w-4 h-4 flex-shrink-0" />
              <span className="text-[8px] font-heading tracking-wider truncate">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
