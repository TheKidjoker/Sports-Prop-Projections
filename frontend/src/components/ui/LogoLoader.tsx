import { useState, useEffect } from "react";
import { motion, useReducedMotion } from "framer-motion";

interface LogoLoaderProps {
  text?: string;
  size?: "sm" | "md" | "lg";
  fullScreen?: boolean;
}

const sizes = {
  sm: { img: "w-10 h-10", orbit: 28 },
  md: { img: "w-16 h-16", orbit: 40 },
  lg: { img: "w-28 h-28", orbit: 64 },
};

const BOOT_MESSAGES = [
  "INITIALIZING SYSTEMS...",
  "CALIBRATING MODELS...",
  "LOADING INTEL...",
  "SCANNING NETWORKS...",
  "COMPILING DATA...",
];

export function LogoLoader({ text, size = "md", fullScreen = false }: LogoLoaderProps) {
  const prefersReduced = useReducedMotion();
  const [msgIndex, setMsgIndex] = useState(0);
  const s = sizes[size];

  useEffect(() => {
    if (prefersReduced) return;
    const id = setInterval(() => {
      setMsgIndex((i) => (i + 1) % BOOT_MESSAGES.length);
    }, 2000);
    return () => clearInterval(id);
  }, [prefersReduced]);

  const displayText = text ?? BOOT_MESSAGES[msgIndex];

  const content = (
    <div className="flex flex-col items-center gap-4">
      <div className="relative">
        {/* Orbiting dots */}
        {!prefersReduced && (
          <svg
            className="absolute inset-0"
            style={{ width: parseInt(s.img) + s.orbit, height: parseInt(s.img) + s.orbit, left: -s.orbit / 2, top: -s.orbit / 2 }}
            viewBox={`0 0 ${100 + s.orbit} ${100 + s.orbit}`}
          >
            <motion.circle
              cx={50 + s.orbit / 2}
              cy={s.orbit / 2}
              r={2}
              fill="hsl(0, 72%, 51%)"
              animate={{ rotate: 360 }}
              transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
              style={{ transformOrigin: `${50 + s.orbit / 2}px ${50 + s.orbit / 2}px`, filter: "drop-shadow(0 0 4px hsl(0, 72%, 51%))" }}
            />
            <motion.circle
              cx={50 + s.orbit / 2}
              cy={100 + s.orbit / 2}
              r={1.5}
              fill="hsl(43, 76%, 38%)"
              animate={{ rotate: -360 }}
              transition={{ duration: 5, repeat: Infinity, ease: "linear" }}
              style={{ transformOrigin: `${50 + s.orbit / 2}px ${50 + s.orbit / 2}px`, filter: "drop-shadow(0 0 3px hsl(43, 76%, 38%))" }}
            />
          </svg>
        )}
        <motion.img
          src="/static/logo.png"
          alt="Loading"
          className={`${s.img}`}
          style={{ filter: "drop-shadow(0 0 20px hsla(0, 72%, 51%, 0.4))" }}
          animate={prefersReduced ? {} : { rotate: 360 }}
          transition={prefersReduced ? {} : { duration: 3, repeat: Infinity, ease: "linear" }}
        />
        {/* Scanline overlay on logo */}
        {!prefersReduced && (
          <div className="absolute inset-0 overflow-hidden pointer-events-none">
            <div
              className="w-full h-[2px] animate-jarvis-scan"
              style={{ background: "linear-gradient(90deg, transparent, hsla(0, 72%, 51%, 0.3), transparent)" }}
            />
          </div>
        )}
      </div>
      <span className="text-primary font-mono text-[10px] sm:text-xs tracking-wider animate-boot-text">
        {displayText}
      </span>
    </div>
  );

  if (fullScreen) {
    return (
      <div className="min-h-screen bg-background hex-grid-bg flex items-center justify-center">
        {content}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center py-12">
      {content}
    </div>
  );
}
