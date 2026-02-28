interface FeatureImportance {
  feature: string;
  importance: number;
}

interface TmFeatureImportancesProps {
  features: FeatureImportance[];
  title?: string;
  maxItems?: number;
}

export function TmFeatureImportances({
  features,
  title = "Feature Importances",
  maxItems = 15,
}: TmFeatureImportancesProps) {
  if (!features || features.length === 0) return null;

  const sorted = [...features]
    .sort((a, b) => Math.abs(b.importance) - Math.abs(a.importance))
    .slice(0, maxItems);

  const maxVal = Math.max(...sorted.map((f) => Math.abs(f.importance)), 0.01);

  return (
    <div>
      {title && (
        <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-3 uppercase">
          {title}
        </h4>
      )}
      <div className="space-y-1.5">
        {sorted.map((f) => {
          const pct = (Math.abs(f.importance) / maxVal) * 100;
          const isPositive = f.importance >= 0;
          return (
            <div key={f.feature} className="flex items-center gap-2">
              <span className="text-xs font-mono text-muted-foreground w-36 truncate text-right">
                {f.feature}
              </span>
              <div className="flex-1 h-4 bg-muted rounded-sm overflow-hidden">
                <div
                  className={`h-full rounded-sm transition-all ${
                    isPositive ? "bg-green-500/60" : "bg-red-500/60"
                  }`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="text-xs font-mono w-14 text-right text-muted-foreground">
                {f.importance.toFixed(3)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
