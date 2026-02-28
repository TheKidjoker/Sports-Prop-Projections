interface Comparison {
  rules_accuracy: number;
  rules_roi: number;
  ml_accuracy?: number;
  ml_roi?: number;
  ml_clv?: number;
}

interface TmComparisonTableProps {
  comparison: Comparison;
}

export function TmComparisonTable({ comparison }: TmComparisonTableProps) {
  const rows = [
    {
      label: "Accuracy",
      rules: `${comparison.rules_accuracy.toFixed(1)}%`,
      ml: comparison.ml_accuracy != null ? `${comparison.ml_accuracy.toFixed(1)}%` : "—",
    },
    {
      label: "ROI",
      rules: `${comparison.rules_roi > 0 ? "+" : ""}${comparison.rules_roi.toFixed(1)}%`,
      ml: comparison.ml_roi != null ? `${comparison.ml_roi > 0 ? "+" : ""}${comparison.ml_roi.toFixed(1)}%` : "—",
    },
    {
      label: "CLV Avg",
      rules: "—",
      ml: comparison.ml_clv != null ? comparison.ml_clv.toFixed(2) : "—",
    },
  ];

  return (
    <div>
      <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-2 uppercase">
        Rules vs ML Comparison
      </h4>
      <div className="rounded-sm border border-border overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-muted/50">
              <th className="px-3 py-2 text-left text-xs font-heading tracking-wider text-muted-foreground">Metric</th>
              <th className="px-3 py-2 text-right text-xs font-heading tracking-wider text-primary">Rules</th>
              <th className="px-3 py-2 text-right text-xs font-heading tracking-wider text-secondary">ML</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-border">
                <td className="px-3 py-2 text-sm font-mono text-muted-foreground">{r.label}</td>
                <td className="px-3 py-2 text-sm font-mono text-right text-foreground">{r.rules}</td>
                <td className="px-3 py-2 text-sm font-mono text-right text-foreground">{r.ml}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
