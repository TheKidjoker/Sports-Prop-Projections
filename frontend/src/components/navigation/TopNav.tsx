import { Bell, LogOut, Shield } from "lucide-react";
import { SportPills, type Sport } from "./SportPills";

interface TopNavProps {
  selectedSport: Sport | null;
  onSelectSport: (sport: Sport | null) => void;
  isAdmin?: boolean;
}

export function TopNav({ selectedSport, onSelectSport, isAdmin = false }: TopNavProps) {
  return (
    <header className="h-14 border-b border-border glass sticky top-0 z-40">
      <div className="h-full flex items-center justify-between px-4">
        {/* Logo */}
        <div className="flex items-center gap-2 min-w-[160px]">
          <h1 className="text-lg font-heading tracking-[0.15em] text-foreground">
            <span className="text-primary">JOKER'S</span>{" "}
            <span className="text-secondary">EDGE</span>
          </h1>
        </div>

        {/* Sport Pills - center */}
        <div className="hidden md:flex">
          <SportPills selected={selectedSport} onSelect={onSelectSport} />
        </div>

        {/* Right actions */}
        <div className="flex items-center gap-2 min-w-[160px] justify-end">
          {isAdmin && (
            <button className="p-2 text-secondary hover:text-secondary/80 transition-colors" title="Admin">
              <Shield className="w-4 h-4" />
            </button>
          )}
          <button className="p-2 text-muted-foreground hover:text-foreground transition-colors relative">
            <Bell className="w-4 h-4" />
            <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-primary rounded-full" />
          </button>
          <button className="p-2 text-muted-foreground hover:text-foreground transition-colors">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
