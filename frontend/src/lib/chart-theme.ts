// JARVIS Chart Theme — shared constants for all Recharts visualizations

export const CHART_COLORS = {
  crimson: "hsl(0, 72%, 51%)",
  crimsonMuted: "hsla(0, 72%, 51%, 0.3)",
  gold: "hsl(43, 76%, 38%)",
  goldMuted: "hsla(43, 76%, 38%, 0.3)",
  green: "hsl(142, 71%, 45%)",
  greenMuted: "hsla(142, 71%, 45%, 0.3)",
  muted: "hsl(0, 0%, 53%)",
  grid: "hsla(0, 0%, 100%, 0.06)",
  background: "hsl(240, 20%, 4%)",
  surface: "hsl(240, 15%, 7%)",
  foreground: "hsl(0, 0%, 96%)",
  foregroundMuted: "hsl(0, 0%, 53%)",
} as const;

export const CHART_FONTS = {
  axis: "'JetBrains Mono', monospace",
  label: "'Oswald', sans-serif",
} as const;

export const CHART_AXIS_STYLE = {
  fontSize: 10,
  fontFamily: CHART_FONTS.axis,
  fill: CHART_COLORS.foregroundMuted,
} as const;

export const CHART_GRID_STYLE = {
  strokeDasharray: "3 3",
  stroke: CHART_COLORS.grid,
} as const;
