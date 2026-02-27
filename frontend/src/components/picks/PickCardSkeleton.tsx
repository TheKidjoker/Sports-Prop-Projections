export function PickCardSkeleton() {
  return (
    <div className="card-surface rounded-sm border-l-tier-monitor overflow-hidden">
      <div className="px-4 pt-3 pb-2 flex items-center justify-between">
        <div className="h-4 w-24 bg-primary/10 rounded-sm animate-red-pulse" />
        <div className="h-4 w-16 bg-primary/10 rounded-sm animate-red-pulse" />
      </div>
      <div className="px-4 pb-2">
        <div className="h-6 w-48 bg-primary/10 rounded-sm animate-red-pulse mb-2" />
        <div className="h-3 w-32 bg-primary/10 rounded-sm animate-red-pulse" />
      </div>
      <div className="px-4 py-2 border-t border-b border-border/50">
        <div className="h-4 w-full bg-primary/10 rounded-sm animate-red-pulse" />
      </div>
      <div className="px-4 py-3 flex gap-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-6 w-16 bg-primary/10 rounded-sm animate-red-pulse" />
        ))}
      </div>
    </div>
  );
}
