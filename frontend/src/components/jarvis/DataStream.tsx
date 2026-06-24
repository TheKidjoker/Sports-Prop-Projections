import { useEffect, useRef } from "react";

interface DataStreamProps {
  items: { id: string; label: string; detail?: string; status?: "success" | "error" | "pending" }[];
  speed?: number;
  className?: string;
}

const statusColor = {
  success: "text-success",
  error: "text-primary",
  pending: "text-muted-foreground",
};

export function DataStream({ items, speed = 3000, className = "" }: DataStreamProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [items.length]);

  return (
    <div ref={containerRef} className={`overflow-y-auto font-mono text-[13px] space-y-0.5 ${className}`}>
      {items.map((item) => (
        <div key={item.id} className="flex items-center gap-2 px-2 py-1 hover:bg-muted/20 transition-colors">
          <span className={`w-1 h-1 rounded-full flex-shrink-0 ${statusColor[item.status ?? "pending"]} bg-current`} />
          <span className="text-foreground truncate flex-1">{item.label}</span>
          {item.detail && <span className="text-muted-foreground flex-shrink-0">{item.detail}</span>}
        </div>
      ))}
    </div>
  );
}
