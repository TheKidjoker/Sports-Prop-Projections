import { Home, Crosshair, Users, Target, BookOpen, FileText } from "lucide-react";

interface MobileNavProps {
  activeSection: string;
  onSelectSection: (id: string) => void;
}

const items = [
  { icon: Home, label: "CMD", id: "command" },
  { icon: Crosshair, label: "INTEL", id: "intel" },
  { icon: Users, label: "OPS", id: "operatives" },
  { icon: Target, label: "STRIKE", id: "strike-ops" },
  { icon: BookOpen, label: "WAR RM", id: "war-room" },
  { icon: FileText, label: "LOG", id: "field-log" },
];

export function MobileNav({ activeSection, onSelectSection }: MobileNavProps) {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 glass border-t border-border pb-[env(safe-area-inset-bottom)]">
      <div className="flex items-center justify-around h-14">
        {items.map((item) => {
          const active = activeSection === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectSection(item.id)}
              className={`flex flex-col items-center gap-0.5 py-1 px-1 min-w-0 transition-colors relative ${
                active ? "text-primary" : "text-muted-foreground"
              }`}
            >
              <item.icon className="w-4 h-4 flex-shrink-0" />
              <span className="text-[7px] font-heading tracking-wider truncate">{item.label}</span>
              {active && (
                <div
                  className="absolute -bottom-0 left-1/2 -translate-x-1/2 w-6 h-[2px] bg-primary rounded-full"
                  style={{ boxShadow: "0 0 8px hsla(0, 72%, 51%, 0.5)" }}
                />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
