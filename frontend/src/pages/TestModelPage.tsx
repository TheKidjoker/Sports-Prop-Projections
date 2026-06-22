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
import { HudPanel } from "@/components/jarvis/HudPanel";
import { HexBadge } from "@/components/jarvis/HexBadge";
import { CHART_COLORS } from "@/lib/chart-theme";

const SPORTS: Sport[] = ["NBA", "NHL", "MLB", "NFL", "CFB", "CBB"];

/* ── per-sport hex badge colors ── */
const sportHexColor: Record<string, string> = {
  NBA: CHART_COLORS.crimson,
  NHL: "#60a5fa",
  MLB: CHART_COLORS.green,
  NFL: CHART_COLORS.gold,
  CFB: "#f97316",
  CBB: "#c084fc",
};

/* ── Tab definitions ── */
const TABS = [
  { value: "scan",        label: "TODAY'S MODEL" },
  { value: "backtest",    label: "BACKTEST" },
  { value: "rules",       label: "RULES REPLAY" },
  { value: "calibration", label: "CALIBRATION" },
  { value: "collection",  label: "DATA" },
  { value: "metrics",     label: "METRICS" },
] as const;

interface TestModelPageProps {
  sport: Sport | null;
}

export function TestModelPage({ sport: _globalSport }: TestModelPageProps) {
  const [tmSport, setTmSport] = useState<Sport>("NBA");
  const lowerSport = tmSport.toLowerCase() as SportLower;

  return (
    <div className="py-4 sm:py-6 px-3 sm:px-6 max-w-6xl mx-auto space-y-4">
      {/* ── Page Header ── */}
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg sm:text-xl tracking-widest text-foreground uppercase">
          Diagnostics{" "}
          <span style={{ color: CHART_COLORS.crimson }}>/ Model Laboratory</span>
        </h2>
      </div>

      {/* ── Sport Switcher (HexBadge row) ── */}
      <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto pb-1">
        {SPORTS.map((s) => (
          <HexBadge
            key={s}
            label={s}
            color={sportHexColor[s] ?? CHART_COLORS.muted}
            size="md"
            active={tmSport === s}
            onClick={() => setTmSport(s)}
          />
        ))}
      </div>

      {/* ── Command Tabs ── */}
      <Tabs defaultValue="scan" className="space-y-4">
        <HudPanel>
          <TabsList className="bg-transparent border-0 h-auto flex-wrap gap-1 p-0">
            {TABS.map(({ value, label }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="text-[9px] sm:text-[10px] font-heading tracking-widest uppercase px-3 sm:px-4 py-1.5 border transition-all rounded-none
                  data-[state=inactive]:border-white/[0.06] data-[state=inactive]:bg-transparent data-[state=inactive]:text-muted-foreground
                  data-[state=active]:border-[hsla(0,72%,51%,0.5)] data-[state=active]:bg-[hsla(0,72%,51%,0.1)] data-[state=active]:text-[hsl(0,72%,51%)]"
                style={{ clipPath: "polygon(6% 0%, 94% 0%, 100% 50%, 94% 100%, 6% 100%, 0% 50%)" }}
              >
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
        </HudPanel>

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

      {/* ── Legend ── */}
      <div className="mt-6">
        <HudPanel title="SYSTEM LEGEND" status="online">
          <TmLegend />
        </HudPanel>
      </div>
    </div>
  );
}
