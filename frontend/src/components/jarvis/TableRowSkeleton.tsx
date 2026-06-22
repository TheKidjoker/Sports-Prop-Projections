export function TableRowSkeleton({ cols = 6 }: { cols?: number }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 border-b border-border/30">
      {Array.from({ length: cols }).map((_, i) => (
        <div key={i} className={`h-3 bg-primary/10 rounded-sm animate-red-pulse ${i === 0 ? "flex-1" : "w-12"}`} />
      ))}
    </div>
  );
}
