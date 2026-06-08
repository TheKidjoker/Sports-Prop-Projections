import { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CollectionPanel } from "@/components/test-model/CollectionPanel";
import { MetricsPanel } from "@/components/test-model/MetricsPanel";
import { CalibrationPanel } from "@/components/test-model/CalibrationPanel";
import { BacktestPanel } from "@/components/test-model/BacktestPanel";
import { ScanPanel } from "@/components/test-model/ScanPanel";
import { RulesPanel } from "@/components/test-model/RulesPanel";
import { TmLegend } from "@/components/test-model/TmLegend";
import type { Sport, SportLower } from "@/lib/types";

const SPORTS: Sport[] = ["NBA", "NHL", "MLB", "NFL", "CFB", "CBB"];

interface TestModelPageProps {
  sport: Sport | null;
}

export function TestModelPage({ sport: _globalSport }: TestModelPageProps) {
  const [tmSport, setTmSport] = useState<Sport>("NBA");
  const lowerSport = tmSport.toLowerCase() as SportLower;

  return (
    <div className="py-4 sm:py-6 px-3 sm:px-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-4 sm:mb-6">
        <h2 className="font-heading text-lg sm:text-xl tracking-wider text-foreground">
          TEST <span className="text-primary">MODEL</span>
        </h2>
      </div>

      {/* Sport switcher pills */}
      <div className="flex items-center gap-1 sm:gap-1.5 mb-4 sm:mb-6 overflow-x-auto">
        {SPORTS.map((s) => (
          <button
            key={s}
            onClick={() => setTmSport(s)}
            className={`px-3 py-1.5 text-xs font-heading tracking-wider rounded-sm transition-colors ${
              tmSport === s
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-muted-foreground hover:text-foreground hover:bg-muted/80"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <Tabs defaultValue="scan" className="space-y-4">
        <TabsList className="bg-muted/50 border border-border rounded-sm h-auto flex-wrap gap-0.5 p-1">
          {([
            ["scan", "TODAY'S MODEL"],
            ["backtest", "BACKTEST"],
            ["rules", "RULES REPLAY"],
            ["calibration", "CALIBRATION"],
            ["collection", "DATA"],
            ["metrics", "METRICS"],
          ] as const).map(([val, label]) => (
            <TabsTrigger
              key={val}
              value={val}
              className="text-[10px] sm:text-xs font-heading tracking-wider data-[state=active]:bg-primary data-[state=active]:text-primary-foreground rounded-sm px-2 sm:px-3 py-1 sm:py-1.5"
            >
              {label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="scan">
          <ScanPanel key={lowerSport} sport={lowerSport} />
        </TabsContent>

        <TabsContent value="backtest">
          <BacktestPanel key={lowerSport} sport={lowerSport} />
        </TabsContent>

        <TabsContent value="rules">
          <RulesPanel key={lowerSport} sport={lowerSport} />
        </TabsContent>

        <TabsContent value="calibration">
          <CalibrationPanel key={lowerSport} sport={lowerSport} />
        </TabsContent>

        <TabsContent value="collection">
          <CollectionPanel key={lowerSport} sport={lowerSport} />
        </TabsContent>

        <TabsContent value="metrics">
          <MetricsPanel key={lowerSport} sport={lowerSport} />
        </TabsContent>
      </Tabs>

      {/* Legend at bottom */}
      <div className="mt-8">
        <TmLegend />
      </div>
    </div>
  );
}
