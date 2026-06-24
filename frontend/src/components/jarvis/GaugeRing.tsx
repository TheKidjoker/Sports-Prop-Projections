import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

interface GaugeRingProps {
  value: number;
  max?: number;
  label: string;
  unit?: string;
  size?: number;
  color?: string;
  className?: string;
}

export function GaugeRing({ value, max = 100, label, unit = "%", size = 80, color = "hsl(0, 72%, 51%)", className = "" }: GaugeRingProps) {
  const prefersReduced = useReducedMotion();
  const [displayed, setDisplayed] = useState(prefersReduced ? value : 0);
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(Math.max(displayed / max, 0), 1);
  const offset = circumference * (1 - pct);

  useEffect(() => {
    if (prefersReduced) { setDisplayed(value); return; }
    const start = displayed;
    const diff = value - start;
    const duration = 800;
    const startTime = performance.now();
    function tick(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayed(start + diff * eased);
      if (progress < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  const displayValue = unit === "%" ? displayed.toFixed(1) : Math.round(displayed).toString();

  return (
    <div className={`flex flex-col items-center gap-1 ${className}`} aria-label={`${label}: ${displayValue}${unit}`}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="transform -rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="hsla(0,0%,100%,0.06)" strokeWidth={4} />
          <circle
            cx={size / 2} cy={size / 2} r={radius} fill="none"
            stroke={color} strokeWidth={4} strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={offset}
            style={{ transition: prefersReduced ? "none" : "stroke-dashoffset 0.8s cubic-bezier(0.33,1,0.68,1)", filter: `drop-shadow(0 0 4px ${color})` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono text-foreground leading-none" style={{ fontSize: size * 0.22 }}>{displayValue}</span>
          <span className="text-muted-foreground leading-none" style={{ fontSize: Math.max(8, size * 0.11) }}>{unit}</span>
        </div>
      </div>
      <span className="font-heading text-[12px] tracking-wider text-muted-foreground text-center leading-tight">{label}</span>
    </div>
  );
}
