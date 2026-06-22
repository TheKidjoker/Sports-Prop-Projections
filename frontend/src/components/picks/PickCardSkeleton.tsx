export function PickCardSkeleton() {
  return (
    <div className="hud-panel" style={{ borderLeft: "3px solid hsla(0, 72%, 51%, 0.2)" }}>
      <div className="px-4 pt-3 pb-2 flex items-center justify-between">
        <div className="h-5 w-24 bg-primary/10 animate-red-pulse" style={{ clipPath: "polygon(8% 0%, 92% 0%, 100% 50%, 92% 100%, 8% 100%, 0% 50%)" }} />
        <div className="h-12 w-12 rounded-full border-2 border-primary/15 animate-red-pulse" />
      </div>
      <div className="px-4 pb-2">
        <div className="h-6 w-48 bg-primary/10 animate-red-pulse mb-2" />
        <div className="h-4 w-32 bg-primary/10 animate-red-pulse" />
      </div>
      <div className="mx-4 py-2 mb-2" style={{ borderLeft: "2px solid hsla(0, 72%, 51%, 0.15)", paddingLeft: 12 }}>
        <div className="h-4 w-full bg-primary/10 animate-red-pulse" />
      </div>
      <div className="px-4 py-3 flex gap-2">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-6 w-16 bg-primary/10 animate-red-pulse" style={{ clipPath: "polygon(4px 0, calc(100% - 4px) 0, 100% 50%, calc(100% - 4px) 100%, 4px 100%, 0 50%)" }} />
        ))}
      </div>
    </div>
  );
}
