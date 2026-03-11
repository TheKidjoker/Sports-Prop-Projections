import { useState } from "react";
import { motion } from "framer-motion";
import {
  Home,
  Zap,
  User,
  Layers,
  BookOpen,
  DollarSign,
  Shield,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const sidebarItems = [
  { icon: Home, label: "Home", id: "home" },
  { icon: Zap, label: "Quick Picks", id: "picks" },
  { icon: User, label: "Player Props", id: "props" },
  { icon: Layers, label: "Parlays", id: "parlays" },
  { icon: BookOpen, label: "The Ledger", id: "ledger" },
  { icon: DollarSign, label: "My Bets", id: "bets" },
  { icon: Shield, label: "Admin", id: "admin", adminOnly: true },
];

interface AppSidebarProps {
  activeSection: string;
  onSelectSection: (id: string) => void;
  isAdmin?: boolean;
}

export function AppSidebar({ activeSection, onSelectSection, isAdmin = false }: AppSidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  const filteredItems = sidebarItems.filter((item) => !item.adminOnly || isAdmin);

  return (
    <motion.aside
      animate={{ width: collapsed ? 56 : 200 }}
      transition={{ duration: 0.2, ease: "easeInOut" }}
      className="hidden lg:flex flex-col border-r border-border bg-sidebar h-[calc(100vh-3.5rem)] sticky top-14 overflow-hidden"
    >
      <nav className="flex-1 py-3">
        {filteredItems.map((item) => {
          const active = activeSection === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectSection(item.id)}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm transition-all duration-150 group ${
                active
                  ? "text-primary bg-sidebar-accent border-l-2 border-l-primary"
                  : "text-sidebar-foreground hover:text-foreground hover:bg-sidebar-accent border-l-2 border-l-transparent"
              }`}
            >
              <item.icon
                className={`w-4 h-4 flex-shrink-0 ${
                  active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
                }`}
              />
              {!collapsed && (
                <span className="font-heading text-xs tracking-wider truncate">
                  {item.label}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <button
        onClick={() => setCollapsed(!collapsed)}
        className="p-3 border-t border-border text-muted-foreground hover:text-foreground transition-colors"
      >
        {collapsed ? <ChevronRight className="w-4 h-4 mx-auto" /> : <ChevronLeft className="w-4 h-4 mx-auto" />}
      </button>
    </motion.aside>
  );
}
