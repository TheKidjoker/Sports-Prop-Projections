import { memo } from "react";
import { LineChart, Line, ResponsiveContainer } from "recharts";

interface MiniSparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
}

export const MiniSparkline = memo(function MiniSparkline({ data, width = 80, height = 24, color = "hsl(0, 72%, 51%)" }: MiniSparklineProps) {
  const chartData = data.map((v, i) => ({ i, v }));
  return (
    <div style={{ width, height }} aria-label={`Sparkline: ${data.length} data points`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
});
