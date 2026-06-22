import { type ReactNode } from "react";
import { motion } from "framer-motion";

interface HudPanelProps {
  title?: string;
  status?: "online" | "warning" | "error" | "offline";
  glow?: boolean;
  headerRight?: ReactNode;
  children: ReactNode;
  className?: string;
}

const statusColors = {
  online: "bg-success",
  warning: "bg-warning",
  error: "bg-primary",
  offline: "bg-muted-foreground",
};

export function HudPanel({ title, status, glow, headerRight, children, className = "" }: HudPanelProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`hud-panel ${glow ? "hud-panel-active" : ""} ${className}`}
    >
      {title && (
        <div className="hud-panel-header">
          {status && (
            <span className={`w-1.5 h-1.5 rounded-full ${statusColors[status]} ${status === "online" ? "animate-pulse-dot" : ""}`} />
          )}
          <span className="text-foreground flex-1">{title}</span>
          {headerRight && <div className="ml-auto">{headerRight}</div>}
        </div>
      )}
      <div className="p-3 sm:p-4">{children}</div>
    </motion.div>
  );
}
