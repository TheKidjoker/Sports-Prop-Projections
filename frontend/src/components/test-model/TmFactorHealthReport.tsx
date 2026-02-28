import type { TmFactorHealth } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface TmFactorHealthReportProps {
  health: TmFactorHealth;
}

export function TmFactorHealthReport({ health }: TmFactorHealthReportProps) {
  return (
    <div className="space-y-4">
      <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground uppercase">
        Factor Health Report
      </h4>

      {/* Standalone Lift */}
      {health.standalone_lift?.length > 0 && (
        <div>
          <h5 className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1 uppercase">
            Standalone Lift
          </h5>
          <div className="rounded-sm border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="text-xs font-heading tracking-wider">Factor</TableHead>
                  <TableHead className="text-xs font-heading tracking-wider text-right">Standalone Acc</TableHead>
                  <TableHead className="text-xs font-heading tracking-wider text-right">Marginal Lift</TableHead>
                  <TableHead className="text-xs font-heading tracking-wider text-right">N</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {health.standalone_lift.map((f) => (
                  <TableRow key={f.factor}>
                    <TableCell className="font-mono text-sm">{f.factor}</TableCell>
                    <TableCell className="font-mono text-sm text-right">
                      {f.standalone_acc.toFixed(1)}%
                    </TableCell>
                    <TableCell
                      className={`font-mono text-sm text-right ${
                        f.marginal_lift > 0 ? "text-green-400" : "text-red-400"
                      }`}
                    >
                      {f.marginal_lift > 0 ? "+" : ""}
                      {f.marginal_lift.toFixed(1)}%
                    </TableCell>
                    <TableCell className="font-mono text-sm text-right">{f.n}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* VIF */}
      {health.vif?.length > 0 && (
        <div>
          <h5 className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1 uppercase">
            Variance Inflation Factor
          </h5>
          <div className="rounded-sm border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="text-xs font-heading tracking-wider">Factor</TableHead>
                  <TableHead className="text-xs font-heading tracking-wider text-right">VIF</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {health.vif.map((f) => (
                  <TableRow key={f.factor}>
                    <TableCell className="font-mono text-sm">{f.factor}</TableCell>
                    <TableCell
                      className={`font-mono text-sm text-right ${
                        f.vif > 5 ? "text-red-400" : f.vif > 3 ? "text-yellow-400" : "text-green-400"
                      }`}
                    >
                      {f.vif.toFixed(2)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* Correlations */}
      {health.correlations?.length > 0 && (
        <div>
          <h5 className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1 uppercase">
            High Correlations
          </h5>
          <div className="space-y-1">
            {health.correlations.map((c) => (
              <div key={c.pair} className="flex items-center gap-2 text-xs">
                <span className="font-mono text-muted-foreground">{c.pair}:</span>
                <span
                  className={`font-mono ${
                    Math.abs(c.corr) > 0.6 ? "text-red-400" : "text-yellow-400"
                  }`}
                >
                  r={c.corr.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recommendations */}
      {health.recommendations?.length > 0 && (
        <div>
          <h5 className="text-[10px] font-heading tracking-wider text-muted-foreground mb-1 uppercase">
            Recommendations
          </h5>
          <ul className="space-y-1">
            {health.recommendations.map((r, i) => (
              <li key={i} className="text-xs text-muted-foreground font-mono">
                - {r}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
