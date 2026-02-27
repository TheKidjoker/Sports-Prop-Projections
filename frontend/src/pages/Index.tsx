import { useState } from "react";
import { TopNav } from "../components/navigation/TopNav";
import { AppSidebar } from "../components/navigation/AppSidebar";
import { GameTicker } from "../components/navigation/GameTicker";
import { MobileNav } from "../components/navigation/MobileNav";
import { HeroSection } from "../components/home/HeroSection";
import { ScanResults } from "../components/picks/ScanResults";
import { SportPills, type Sport } from "../components/navigation/SportPills";

const Index = () => {
  const [selectedSport, setSelectedSport] = useState<Sport | null>(null);
  const [activeSection, setActiveSection] = useState("picks");
  const [scanning, setScanning] = useState(false);

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

  return (
    <div className="min-h-screen bg-background">
      <TopNav
        selectedSport={selectedSport}
        onSelectSport={handleSelectSport}
        isAdmin
      />
      <GameTicker />

      {/* Mobile sport pills */}
      <div className="md:hidden overflow-x-auto px-4 py-2 border-b border-border">
        <SportPills selected={selectedSport} onSelect={handleSelectSport} />
      </div>

      <div className="flex w-full">
        <AppSidebar
          activeSection={activeSection}
          onSelectSection={setActiveSection}
          isAdmin
        />

        <main className="flex-1 pb-20 lg:pb-0">
          {!scanning ? (
            <HeroSection
              onSelectSport={(sport) => handleSelectSport(sport)}
              onScan={handleScan}
              selectedSport={selectedSport}
            />
          ) : selectedSport ? (
            <ScanResults sport={selectedSport} isAdmin />
          ) : (
            <HeroSection
              onSelectSport={(sport) => handleSelectSport(sport)}
              onScan={handleScan}
              selectedSport={selectedSport}
            />
          )}
        </main>
      </div>

      <MobileNav activeSection={activeSection} onSelectSection={setActiveSection} />
    </div>
  );
};

export default Index;
