import type { TmThresholdEntry } from "@/lib/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface TmThresholdTableProps {
  rows: TmThresholdEntry[];
  title?: string;
}

export function TmThresholdTable({ rows, title }: TmThresholdTableProps) {
  if (!rows || rows.length === 0) return null;

  return (
    <div>
      {title && (
        <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-2 uppercase">
          {title}
        </h4>
      )}
      <div className="rounded-sm border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50">
              <TableHead className="text-xs font-heading tracking-wider">Score &ge;</TableHead>
              <TableHead className="text-xs font-heading tracking-wider text-right">Bets</TableHead>
              <TableHead className="text-xs font-heading tracking-wider text-right">Accuracy</TableHead>
              <TableHead className="text-xs font-heading tracking-wider text-right">ROI</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.threshold}>
                <TableCell className="font-mono text-sm">{r.threshold}</TableCell>
                <TableCell className="font-mono text-sm text-right">{r.count}</TableCell>
                <TableCell
                  className={`font-mono text-sm text-right ${
                    r.accuracy >= 60 ? "text-green-400" : r.accuracy >= 50 ? "text-yellow-400" : "text-red-400"
                  }`}
                >
                  {r.accuracy.toFixed(1)}%
                </TableCell>
                <TableCell
                  className={`font-mono text-sm text-right ${
                    r.roi > 0 ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {r.roi > 0 ? "+" : ""}
                  {r.roi.toFixed(1)}%
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
