interface HexBadgeProps {
  label: string;
  color?: string;
  size?: "sm" | "md";
  active?: boolean;
  className?: string;
  onClick?: () => void;
}

const sizeStyles = {
  sm: "px-2 py-0.5 text-[11px]",
  md: "px-3 py-1 text-[13px]",
};

export function HexBadge({ label, color = "hsl(0,72%,51%)", size = "sm", active, className = "", onClick }: HexBadgeProps) {
  const Component = onClick ? "button" : "span";
  return (
    <Component
      onClick={onClick}
      className={`inline-flex items-center font-heading tracking-wider border transition-all duration-200 ${sizeStyles[size]} ${className}`}
      style={{
        clipPath: "polygon(8% 0%, 92% 0%, 100% 50%, 92% 100%, 8% 100%, 0% 50%)",
        borderColor: active ? color : "hsla(0,30%,12%,0.6)",
        backgroundColor: active ? `${color}20` : "hsla(240,15%,7%,0.8)",
        color: active ? color : "hsl(0,0%,53%)",
        boxShadow: active ? `0 0 8px ${color}40` : "none",
      }}
    >
      {label}
    </Component>
  );
}
