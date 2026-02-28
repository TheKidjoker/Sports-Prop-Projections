import type { TmFactorEntry } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface TmFactorBreakdownProps {
  factors: TmFactorEntry[];
}

export function TmFactorBreakdown({ factors }: TmFactorBreakdownProps) {
  if (!factors || factors.length === 0) return null;

  const sorted = [...factors].sort((a, b) => b.lift - a.lift);

  return (
    <div>
      <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-2 uppercase">
        Factor Breakdown
      </h4>
      <div className="rounded-sm border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="text-xs font-heading tracking-wider">Factor</TableHead>
              <TableHead className="text-xs font-heading tracking-wider text-right">Fired</TableHead>
              <TableHead className="text-xs font-heading tracking-wider text-right">Acc (Fired)</TableHead>
              <TableHead className="text-xs font-heading tracking-wider text-right">Acc (Not)</TableHead>
              <TableHead className="text-xs font-heading tracking-wider text-right">Lift %</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((f) => (
              <TableRow key={f.factor}>
                <TableCell className="font-mono text-sm">{f.factor}</TableCell>
                <TableCell className="font-mono text-sm text-right">{f.fired}</TableCell>
                <TableCell
                  className={`font-mono text-sm text-right ${
                    f.acc_fired >= 60 ? "text-green-400" : f.acc_fired >= 50 ? "text-yellow-400" : "text-red-400"
                  }`}
                >
                  {f.acc_fired.toFixed(1)}%
                </TableCell>
                <TableCell className="font-mono text-sm text-right">
                  {f.acc_not_fired.toFixed(1)}%
                </TableCell>
                <TableCell
                  className={`font-mono text-sm text-right ${
                    f.lift > 0 ? "text-green-400" : f.lift < 0 ? "text-red-400" : "text-muted-foreground"
                  }`}
                >
                  {f.lift > 0 ? "+" : ""}
                  {f.lift.toFixed(1)}%
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
