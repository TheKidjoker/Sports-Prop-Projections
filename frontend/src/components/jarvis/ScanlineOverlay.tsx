interface ScanlineOverlayProps {
  active?: boolean;
  color?: string;
}

export function ScanlineOverlay({ active = true, color = "hsla(0, 72%, 51%, 0.1)" }: ScanlineOverlayProps) {
  if (!active) return null;
  return (
    <div
      className="pointer-events-none absolute inset-0 z-10 overflow-hidden"
      aria-hidden="true"
    >
      <div
        className="w-full h-[2px] animate-jarvis-scan"
        style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
      />
    </div>
  );
}
