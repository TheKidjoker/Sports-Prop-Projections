import { useState, useCallback } from "react";
import { TopNav } from "../components/navigation/TopNav";
import { AppSidebar } from "../components/navigation/AppSidebar";
import { GameTicker } from "../components/navigation/GameTicker";
import { MobileNav } from "../components/navigation/MobileNav";
import { HeroSection } from "../components/home/HeroSection";
import { ScanResults } from "../components/picks/ScanResults";
import { SportPills } from "../components/navigation/SportPills";
import { PropsPage } from "./PropsPage";
import { LedgerPage } from "./LedgerPage";
import { MyBetsPage } from "./MyBetsPage";
import { AdminPage } from "./AdminPage";
import { TestModelPage } from "./TestModelPage";
import { BetSlip, type BetSlipItem } from "@/components/bets/BetSlip";
import { useAuth } from "@/lib/auth";
import type { Sport } from "@/lib/types";

function LoginForm() {
  const { signIn, signUp } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [isSignUp, setIsSignUp] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (isSignUp) {
        await signUp(email, password);
        setError("Check your email to confirm your account.");
        setIsSignUp(false);
      } else {
        await signIn(email, password);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="card-surface rounded-sm p-8 max-w-sm w-full">
        <h1 className="text-2xl font-heading tracking-[0.15em] text-foreground mb-1 text-center">
          <span className="text-primary">JOKER'S</span>{" "}
          <span className="text-secondary">EDGE</span>
        </h1>
        <p className="text-xs text-muted-foreground text-center mb-6 font-heading tracking-wider">
          {isSignUp ? "CREATE AN ACCOUNT" : "SIGN IN TO CONTINUE"}
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 bg-muted border border-border rounded-sm text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 bg-muted border border-border rounded-sm text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
          />
          {error && (
            <p className="text-xs text-primary">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 bg-primary text-primary-foreground font-heading tracking-[0.15em] text-sm rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {loading
              ? isSignUp ? "CREATING ACCOUNT..." : "SIGNING IN..."
              : isSignUp ? "SIGN UP" : "SIGN IN"}
          </button>
        </form>
        <p className="text-xs text-muted-foreground text-center mt-4">
          {isSignUp ? "Already have an account?" : "Don't have an account?"}{" "}
          <button
            type="button"
            onClick={() => { setIsSignUp(!isSignUp); setError(""); }}
            className="text-primary hover:underline font-heading tracking-wider"
          >
            {isSignUp ? "Sign In" : "Sign Up"}
          </button>
        </p>
      </div>
    </div>
  );
}

const Index = () => {
  const { isLoading, isAuthenticated, isAdmin } = useAuth();
  const [selectedSport, setSelectedSport] = useState<Sport | null>(null);
  const [activeSection, setActiveSection] = useState("picks");
  const [scanning, setScanning] = useState(false);
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
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-primary font-heading tracking-wider animate-pulse">LOADING...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginForm />;
  }

  const handleScan = () => {
    if (selectedSport) {
      setScanning(true);
      setActiveSection("picks");
    }
  };

  const handleSelectSport = (sport: Sport | null) => {
    setSelectedSport(sport);
    if (sport) {
      setScanning(true);
      setActiveSection("picks");
    } else {
      setScanning(false);
    }
  };

  const handleHome = () => {
    setSelectedSport(null);
    setScanning(false);
    setActiveSection("picks");
  };

  const handleSelectSection = (id: string) => {
    if (id === "home") {
      handleHome();
    } else {
      setActiveSection(id);
    }
  };

  const renderContent = () => {
    switch (activeSection) {
      case "props":
        return <PropsPage sport={selectedSport} onTrackBet={addBet} />;
      case "ledger":
        return <LedgerPage sport={selectedSport} />;
      case "bets":
        return <MyBetsPage sport={selectedSport} />;
      case "test":
        return <TestModelPage sport={selectedSport} />;
      case "admin":
        if (isAdmin) return <AdminPage sport={selectedSport} />;
        return null;
      case "picks":
      default:
        if (!scanning) {
          return (
            <HeroSection
              onSelectSport={(sport) => handleSelectSport(sport)}
              onScan={handleScan}
              selectedSport={selectedSport}
            />
          );
        }
        if (selectedSport) {
          return <ScanResults sport={selectedSport} isAdmin={isAdmin} onTrackBet={addBet} />;
        }
        return (
          <HeroSection
            onSelectSport={(sport) => handleSelectSport(sport)}
            onScan={handleScan}
            selectedSport={selectedSport}
          />
        );
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <TopNav
        selectedSport={selectedSport}
        onSelectSport={handleSelectSport}
        onAdminClick={() => setActiveSection("admin")}
        onHomeClick={handleHome}
      />
      <GameTicker />

      {/* Mobile sport pills */}
      <div className="md:hidden overflow-x-auto px-4 py-2 border-b border-border">
        <SportPills selected={selectedSport} onSelect={handleSelectSport} />
      </div>

      <div className="flex w-full">
        <AppSidebar
          activeSection={activeSection}
          onSelectSection={handleSelectSection}
          isAdmin={isAdmin}
        />

        <main className="flex-1 pb-20 lg:pb-0">
          {renderContent()}
        </main>
      </div>

      <MobileNav activeSection={activeSection} onSelectSection={handleSelectSection} />

      <BetSlip bets={selectedBets} onRemove={removeBet} onClear={clearBets} />
    </div>
  );
};

export default Index;
