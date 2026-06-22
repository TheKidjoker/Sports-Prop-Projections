import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

interface AnimatedNumberProps {
  value: number;
  precision?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
}

export function AnimatedNumber({ value, precision = 1, prefix = "", suffix = "", className = "" }: AnimatedNumberProps) {
  const prefersReduced = useReducedMotion();
  const [displayed, setDisplayed] = useState(prefersReduced ? value : 0);

  useEffect(() => {
    if (prefersReduced) { setDisplayed(value); return; }
    const start = displayed;
    const diff = value - start;
    const duration = 600;
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

  return (
    <span className={`font-mono tabular-nums ${className}`}>
      {prefix}{displayed.toFixed(precision)}{suffix}
    </span>
  );
}
