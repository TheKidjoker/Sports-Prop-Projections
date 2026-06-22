import { useState, useCallback, lazy, Suspense } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TopNav } from "../components/navigation/TopNav";
import { GameTicker } from "../components/navigation/GameTicker";
import { MobileNav } from "../components/navigation/MobileNav";
import { SportPills } from "../components/navigation/SportPills";
import { CommandCenter } from "../components/home/CommandCenter";
import { BetSlip, type BetSlipItem } from "@/components/bets/BetSlip";
import { LogoLoader } from "@/components/ui/LogoLoader";
import { HudPanel } from "@/components/jarvis/HudPanel";
import { ScanlineOverlay } from "@/components/jarvis/ScanlineOverlay";
import { useAuth } from "@/lib/auth";
import type { Sport } from "@/lib/types";

// Lazy-load heavy pages
const ScanResults = lazy(() => import("../components/picks/ScanResults").then(m => ({ default: m.ScanResults })));
const PropsPage = lazy(() => import("./PropsPage").then(m => ({ default: m.PropsPage })));
const ParlayPage = lazy(() => import("./ParlayPage").then(m => ({ default: m.ParlayPage })));
const LedgerPage = lazy(() => import("./LedgerPage").then(m => ({ default: m.LedgerPage })));
const MyBetsPage = lazy(() => import("./MyBetsPage").then(m => ({ default: m.MyBetsPage })));
const TestModelPage = lazy(() => import("./TestModelPage").then(m => ({ default: m.TestModelPage })));
const AdminPage = lazy(() => import("./AdminPage").then(m => ({ default: m.AdminPage })));

function LoginForm() {
  const { signIn, signUp } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [isSignUp, setIsSignUp] = useState(false);
  const [bootPhase, setBootPhase] = useState(0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    setBootPhase(1);
    try {
      if (isSignUp) {
        await signUp(email, password);
        setError("Check your email to confirm your account.");
        setIsSignUp(false);
        setBootPhase(0);
      } else {
        setTimeout(() => setBootPhase(2), 600);
        await signIn(email, password);
        setBootPhase(3);
      }
    } catch (err) {
      setError((err as Error).message);
      setBootPhase(0);
    } finally {
      setLoading(false);
    }
  };

  const bootMessages = ["", "AUTHENTICATING...", "VERIFYING CLEARANCE...", "ACCESS GRANTED"];

  return (
    <div className="min-h-screen bg-background flex items-center justify-center hex-grid-bg relative z-20">
      <div className="hud-panel p-8 max-w-sm w-full mx-4">
        <div className="text-center mb-6">
          <img
            src="/static/logo.png"
            alt="Joker's Edge"
            className="w-20 h-20 mx-auto mb-4"
            style={{ filter: "drop-shadow(0 0 20px hsla(0, 72%, 51%, 0.4))" }}
          />
          <h1 className="text-2xl font-heading tracking-[0.15em] text-foreground mb-1">
            <span className="text-primary">JOKER'S</span>{" "}
            <span className="text-secondary">EDGE</span>
          </h1>
          <p className="text-[10px] text-muted-foreground font-heading tracking-[0.2em]">
            {isSignUp ? "CREATE OPERATIVE ACCOUNT" : "SYSTEM ACCESS REQUIRED"}
          </p>
        </div>

        {bootPhase > 0 && (
          <div className="mb-4 text-center">
            <span className="text-[10px] font-mono text-primary animate-boot-text">
              {bootMessages[bootPhase]}
            </span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 bg-muted border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-colors"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 bg-muted border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/30 transition-colors"
          />
          {error && (
            <p className="text-xs text-primary font-mono">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-primary text-primary-foreground font-heading tracking-[0.15em] text-sm transition-all duration-200 hover:bg-primary/90 active:scale-[0.98] disabled:opacity-50"
          >
            {loading
              ? isSignUp ? "CREATING ACCOUNT..." : "DEPLOYING..."
              : isSignUp ? "REGISTER" : "DEPLOY"}
          </button>
        </form>
        <p className="text-[10px] text-muted-foreground text-center mt-4 font-heading tracking-wider">
          {isSignUp ? "Existing operative?" : "New operative?"}{" "}
          <button
            type="button"
            onClick={() => { setIsSignUp(!isSignUp); setError(""); }}
            className="text-primary hover:underline"
          >
            {isSignUp ? "SIGN IN" : "REGISTER"}
          </button>
        </p>
      </div>
    </div>
  );
}

// Map old section IDs to new ones for compatibility
const SECTION_MAP: Record<string, string> = {
  home: "command",
  picks: "intel",
  props: "operatives",
  parlays: "strike-ops",
  ledger: "war-room",
  bets: "field-log",
  test: "diagnostics",
  admin: "admin",
};

const Index = () => {
  const { isLoading, isAuthenticated, isAdmin } = useAuth();
  const [selectedSport, setSelectedSport] = useState<Sport | null>(null);
  const [activeSection, setActiveSection] = useState("command");
  const [selectedBets, setSelectedBets] = useState<BetSlipItem[]>([]);

  const addBet = useCallback((bet: BetSlipItem) => {
    setSelectedBets((prev) => {
      const key = `${bet.event_id}-${bet.type}-${bet.stat ?? bet.team}`;
      if (prev.some((b) => `${b.event_id}-${b.type}-${b.stat ?? b.team}` === key)) return prev;
      return [...prev, bet];
    });
  }, []);

  const removeBet = useCallback((index: number) => {
    setSelectedBets((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const clearBets = useCallback(() => {
    setSelectedBets([]);
  }, []);

  if (isLoading) {
    return <LogoLoader size="lg" fullScreen />;
  }

  if (!isAuthenticated) {
    return <LoginForm />;
  }

  const handleSelectSport = (sport: Sport | null) => {
    setSelectedSport(sport);
    if (sport && activeSection === "command") {
      setActiveSection("intel");
    }
  };

  const handleSelectSection = (id: string) => {
    // Map old IDs to new if needed
    const mapped = SECTION_MAP[id] ?? id;
    setActiveSection(mapped);
    if (mapped === "command") {
      setSelectedSport(null);
    }
  };

  const renderContent = () => {
    switch (activeSection) {
      case "intel":
        if (selectedSport) {
          return <ScanResults sport={selectedSport} isAdmin={isAdmin} onTrackBet={addBet} />;
        }
        return (
          <div className="py-12 text-center">
            <p className="text-muted-foreground font-heading tracking-wider text-sm">SELECT A SPORT TO BEGIN INTEL SCAN</p>
            <div className="flex justify-center mt-4">
              <SportPills selected={selectedSport} onSelect={handleSelectSport} />
            </div>
          </div>
        );
      case "operatives":
        return <PropsPage sport={selectedSport} onTrackBet={addBet} />;
      case "strike-ops":
        return <ParlayPage onTrackBet={addBet} />;
      case "war-room":
        return <LedgerPage sport={selectedSport} />;
      case "field-log":
        return <MyBetsPage sport={selectedSport} />;
      case "diagnostics":
        return <TestModelPage sport={selectedSport} />;
      case "admin":
        if (isAdmin) return <AdminPage sport={selectedSport} />;
        return null;
      case "command":
      default:
        return <CommandCenter onSelectSport={handleSelectSport} />;
    }
  };

  return (
    <div className="min-h-screen bg-background hex-grid-bg">
      <TopNav
        activeSection={activeSection}
        onSelectSection={handleSelectSection}
        selectedSport={selectedSport}
        onSelectSport={handleSelectSport}
        onAdminClick={() => setActiveSection("admin")}
        betCount={selectedBets.length}
      />
      <GameTicker />

      {/* Mobile sport pills */}
      <div className="md:hidden overflow-x-auto px-3 py-2 border-b border-border">
        <SportPills selected={selectedSport} onSelect={handleSelectSport} />
      </div>

      <main className="flex-1 pb-20 md:pb-0">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeSection}
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.15, exit: { duration: 0.1 } }}
          >
            <Suspense fallback={<LogoLoader text="LOADING MODULE..." />}>
              {renderContent()}
            </Suspense>
          </motion.div>
        </AnimatePresence>
      </main>

      <MobileNav activeSection={activeSection} onSelectSection={handleSelectSection} />

      <BetSlip bets={selectedBets} onRemove={removeBet} onClear={clearBets} />
    </div>
  );
};

export default Index;
