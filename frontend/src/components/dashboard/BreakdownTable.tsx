import type { AggregateStats } from "@/lib/types";

interface BreakdownTableProps {
  data: AggregateStats[];
  labelColumn: string;
}

export function BreakdownTable({ data, labelColumn }: BreakdownTableProps) {
  if (data.length === 0) return null;

  return (
    <div className="card-surface rounded-sm overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border bg-muted/30">
            <th className="text-left px-4 py-2 font-heading tracking-wider text-muted-foreground">
              {labelColumn}
            </th>
            <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">TOTAL</th>
            <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">W</th>
            <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">L</th>
            <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">ACC%</th>
            <th className="text-right px-3 py-2 font-heading tracking-wider text-muted-foreground">ROI%</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.label} className="border-b border-border/30 hover:bg-muted/20">
              <td className="px-4 py-2 font-mono text-foreground">{row.label}</td>
              <td className="text-right px-3 py-2 font-mono text-muted-foreground">{row.total}</td>
              <td className="text-right px-3 py-2 font-mono text-success">{row.wins}</td>
              <td className="text-right px-3 py-2 font-mono text-primary">{row.losses}</td>
              <td className={`text-right px-3 py-2 font-mono ${row.accuracy >= 55 ? "text-success" : "text-foreground"}`}>
                {row.accuracy.toFixed(1)}%
              </td>
              <td className={`text-right px-3 py-2 font-mono ${row.roi >= 0 ? "text-success" : "text-primary"}`}>
                {row.roi >= 0 ? "+" : ""}{row.roi.toFixed(1)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
