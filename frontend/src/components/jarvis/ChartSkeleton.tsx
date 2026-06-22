export function ChartSkeleton({ height = 200, className = "" }: { height?: number; className?: string }) {
  return (
    <div className={`hud-panel ${className}`} style={{ height }}>
      <div className="h-full w-full bg-gradient-to-r from-primary/5 via-primary/10 to-primary/5 animate-red-pulse rounded-sm" />
    </div>
  );
}
