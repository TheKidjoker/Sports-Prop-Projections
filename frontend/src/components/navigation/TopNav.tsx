import { useState } from "react";
import { LogOut, Shield, Menu, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { StatusIndicator } from "@/components/jarvis/StatusIndicator";
import { useAuth } from "@/lib/auth";
import type { Sport } from "@/lib/types";

interface NavTab {
  id: string;
  label: string;
  shortLabel: string;
}

const TABS: NavTab[] = [
  { id: "command", label: "COMMAND CENTER", shortLabel: "CMD" },
  { id: "intel", label: "INTEL", shortLabel: "INTEL" },
  { id: "operatives", label: "OPERATIVES", shortLabel: "OPS" },
  { id: "strike-ops", label: "STRIKE OPS", shortLabel: "STRIKE" },
  { id: "war-room", label: "WAR ROOM", shortLabel: "WAR" },
  { id: "field-log", label: "FIELD LOG", shortLabel: "LOG" },
];

interface TopNavProps {
  activeSection: string;
  onSelectSection: (id: string) => void;
  selectedSport: Sport | null;
  onSelectSport: (sport: Sport | null) => void;
  onAdminClick?: () => void;
  betCount?: number;
}

export function TopNav({ activeSection, onSelectSection, selectedSport, onSelectSport, onAdminClick, betCount = 0 }: TopNavProps) {
  const { isAdmin, signOut } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const activeTab = TABS.find(t => t.id === activeSection) ?? TABS[0];

  return (
    <>
      <header className="h-12 glass sticky top-0 z-40 border-b border-border relative">
        <div className="h-full flex items-center justify-between px-3 gap-2">
          {/* Left: Logo + Status */}
          <div className="flex items-center gap-2 min-w-0 shrink-0">
            <button
              onClick={() => onSelectSection("command")}
              className="flex items-center gap-1.5 hover:opacity-80 transition-opacity"
              title="Command Center"
            >
              <img src="/static/logo.png" alt="Joker's Edge" className="w-6 h-6 flex-shrink-0" />
              <h1 className="hidden sm:block text-sm font-heading tracking-[0.12em] text-foreground whitespace-nowrap">
                <span className="text-primary">JOKER'S</span>{" "}
                <span className="text-secondary">EDGE</span>
              </h1>
            </button>
            <StatusIndicator status="online" className="hidden sm:flex" />
          </div>

          {/* Center: Tabs (desktop) / Active label + hamburger (mobile) */}
          <nav className="hidden md:flex items-center gap-0.5 flex-1 justify-center">
            {TABS.map((tab) => {
              const isActive = activeSection === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => onSelectSection(tab.id)}
                  className={`relative px-3 py-1.5 text-[10px] font-heading tracking-wider transition-all duration-200 ${
                    isActive
                      ? "text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                  style={{
                    clipPath: "polygon(6px 0, calc(100% - 6px) 0, 100% 50%, calc(100% - 6px) 100%, 6px 100%, 0 50%)",
                    background: isActive ? "hsla(0, 72%, 51%, 0.1)" : "transparent",
                  }}
                >
                  {tab.label}
                  {isActive && (
                    <motion.div
                      layoutId="tab-indicator"
                      className="absolute bottom-0 left-2 right-2 h-[2px] bg-primary"
                      style={{ boxShadow: "0 0 8px hsla(0, 72%, 51%, 0.5)" }}
                    />
                  )}
                </button>
              );
            })}
          </nav>

          {/* Mobile: Active tab + menu toggle */}
          <div className="md:hidden flex items-center gap-1 flex-1 justify-center">
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="flex items-center gap-1 text-foreground"
            >
              <span className="font-heading text-[10px] tracking-wider text-primary">{activeTab.label}</span>
              {mobileMenuOpen ? <X className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
            </button>
          </div>

          {/* Right: Sport badges + Admin + Logout */}
          <div className="flex items-center gap-1 shrink-0">
            <div className="hidden lg:flex items-center gap-0.5">
              {(["NHL", "NBA", "MLB", "NFL", "CBB"] as Sport[]).map((s) => (
                <HexBadge
                  key={s}
                  label={s}
                  size="sm"
                  active={selectedSport === s}
                  onClick={() => onSelectSport(selectedSport === s ? null : s)}
                />
              ))}
            </div>
            {isAdmin && (
              <button
                onClick={onAdminClick}
                className="p-1.5 text-secondary hover:text-secondary/80 transition-colors"
                title="Admin Panel"
              >
                <Shield className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={() => signOut()}
              className="p-1.5 text-muted-foreground hover:text-foreground transition-colors"
              title="Sign Out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Animated tracer line */}
        <div className="absolute bottom-0 left-0 right-0 h-[2px] overflow-hidden">
          <div
            className="h-full w-1/3 animate-tracer-line"
            style={{ background: "linear-gradient(90deg, transparent, hsl(0, 72%, 51%), transparent)" }}
          />
        </div>
      </header>

      {/* Mobile command menu overlay */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-x-0 top-12 z-50 glass border-b border-border md:hidden"
          >
            <div className="p-3 space-y-1">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => { onSelectSection(tab.id); setMobileMenuOpen(false); }}
                  className={`w-full text-left px-3 py-2 font-heading text-xs tracking-wider rounded-sm transition-colors ${
                    activeSection === tab.id
                      ? "text-primary bg-primary/10"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
              {isAdmin && (
                <button
                  onClick={() => { onAdminClick?.(); setMobileMenuOpen(false); }}
                  className="w-full text-left px-3 py-2 font-heading text-xs tracking-wider text-secondary hover:bg-secondary/10 rounded-sm transition-colors"
                >
                  ADMIN
                </button>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
