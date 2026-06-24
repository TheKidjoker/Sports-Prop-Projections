import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center border font-heading tracking-wider transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        outline: "text-foreground",
        // Tier badges (spread picks)
        strong: "bg-primary/20 text-primary border-primary/40",
        confident: "bg-secondary/20 text-secondary border-secondary/40",
        lean: "bg-foreground/10 text-foreground border-foreground/20",
        monitor: "bg-muted-foreground/10 text-muted-foreground border-muted-foreground/20",
        // Result badges (bet tracker)
        win: "bg-success/15 text-success border-success/30",
        loss: "bg-primary/15 text-primary border-primary/30",
        push: "bg-warning/15 text-warning border-warning/30",
        pending: "bg-muted text-muted-foreground border-border",
        // Signal badges (props)
        "signal-strong": "bg-success/15 text-success border-success/30",
        "signal-lean": "bg-secondary/15 text-secondary border-secondary/30",
        "signal-pass": "bg-muted text-muted-foreground border-border",
        // Validation badges
        validated: "bg-success/15 text-success border-success/30",
        experimental: "bg-warning/15 text-warning border-warning/30",
        limited: "bg-primary/15 text-primary border-primary/30",
      },
      size: {
        default: "text-[13px] px-2 py-0.5 rounded-sm",
        sm: "text-[12px] px-1.5 py-0.5 rounded-sm",
        xs: "text-[11px] px-1 py-0.5 rounded-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, size, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant, size }), className)} {...props} />;
}

export { Badge, badgeVariants };
