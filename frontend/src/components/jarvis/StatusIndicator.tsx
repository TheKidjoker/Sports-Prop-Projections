interface StatusIndicatorProps {
  status: "online" | "warning" | "error" | "offline";
  label?: string;
  pulse?: boolean;
  className?: string;
}

const colors = {
  online: "bg-success",
  warning: "bg-warning",
  error: "bg-primary",
  offline: "bg-muted-foreground",
};

export function StatusIndicator({ status, label, pulse = true, className = "" }: StatusIndicatorProps) {
  return (
    <div className={`inline-flex items-center gap-1.5 ${className}`}>
      <span className={`w-2 h-2 rounded-full ${colors[status]} ${pulse && status === "online" ? "animate-pulse-dot" : ""}`}
        style={pulse && status === "online" ? { boxShadow: `0 0 6px ${status === "online" ? "hsl(142,71%,45%)" : "transparent"}` } : undefined}
      />
      {label && <span className="font-heading text-[13px] tracking-wider text-muted-foreground">{label}</span>}
    </div>
  );
}
