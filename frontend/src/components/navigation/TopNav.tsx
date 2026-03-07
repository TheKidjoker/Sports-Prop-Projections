import { LogOut, Shield } from "lucide-react";
import { SportPills, type Sport } from "./SportPills";
import { useAuth } from "@/lib/auth";

interface TopNavProps {
  selectedSport: Sport | null;
  onSelectSport: (sport: Sport | null) => void;
  onAdminClick?: () => void;
  onHomeClick?: () => void;
}

export function TopNav({ selectedSport, onSelectSport, onAdminClick, onHomeClick }: TopNavProps) {
  const { isAdmin, signOut } = useAuth();

  return (
    <header className="h-14 border-b border-border glass sticky top-0 z-40">
      <div className="h-full flex items-center justify-between px-4">
        {/* Logo + Home */}
        <div className="flex items-center gap-1.5 sm:gap-2 min-w-0 sm:min-w-[160px]">
          <button
            onClick={onHomeClick}
            className="flex items-center gap-1.5 sm:gap-2 hover:opacity-80 transition-opacity"
            title="Home"
          >
            <img src="/static/logo.png" alt="Joker's Edge" className="w-7 h-7 sm:w-8 sm:h-8 flex-shrink-0" />
            <h1 className="text-sm sm:text-lg font-heading tracking-[0.1em] sm:tracking-[0.15em] text-foreground whitespace-nowrap">
              <span className="text-primary">JOKER'S</span>{" "}
              <span className="text-secondary">EDGE</span>
            </h1>
          </button>
        </div>

        {/* Sport Pills - center */}
        <div className="hidden md:flex">
          <SportPills selected={selectedSport} onSelect={onSelectSport} />
        </div>

        {/* Right actions */}
        <div className="flex items-center gap-1.5 sm:gap-2 min-w-0 sm:min-w-[160px] justify-end">
          {isAdmin && (
            <button
              onClick={onAdminClick}
              className="p-2 text-secondary hover:text-secondary/80 transition-colors"
              title="Admin Panel"
            >
              <Shield className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => signOut()}
            className="p-2 text-muted-foreground hover:text-foreground transition-colors"
            title="Sign Out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
