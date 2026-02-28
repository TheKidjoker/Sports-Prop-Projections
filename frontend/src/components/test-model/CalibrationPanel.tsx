import { useTmCalibration } from "@/hooks/use-test-model";
import { TmStatCards } from "./TmStatCards";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { SportLower } from "@/lib/types";

interface CalibrationPanelProps {
  sport: SportLower;
}

export function CalibrationPanel({ sport }: CalibrationPanelProps) {
  const calQ = useTmCalibration(sport);
  const cal = calQ.data?.calibration;

  return (
    <div className="space-y-4">
      <button
        onClick={() => calQ.refetch()}
        disabled={calQ.isFetching}
        className="px-4 py-2 bg-primary text-primary-foreground font-heading tracking-[0.12em] text-xs rounded-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
      >
        {calQ.isFetching ? "LOADING..." : "LOAD CALIBRATION"}
      </button>

      {calQ.error && (
        <p className="text-xs text-red-400 font-mono">
          Error: {(calQ.error as Error).message}
        </p>
      )}

      {calQ.isSuccess && !cal && (
        <p className="text-xs text-muted-foreground font-mono">
          No calibration data — run Rules Replay first.
        </p>
      )}

      {cal && (
        <>
          <TmStatCards
            cards={[
              {
                label: "Brier Score",
                value: cal.brier.toFixed(4),
                color: cal.brier < 0.22 ? "green" : cal.brier < 0.25 ? "yellow" : "red",
              },
              {
                label: "ECE",
                value: `${(cal.ece * 100).toFixed(1)}%`,
                color: cal.ece < 0.05 ? "green" : cal.ece < 0.10 ? "yellow" : "red",
              },
              { label: "Type", value: cal.type.toUpperCase() },
              {
                label: "Bins",
                value: cal.bins?.length ?? 0,
              },
            ]}
          />

          {cal.logistic && (
            <div className="card-surface rounded-sm p-3">
              <h4 className="font-heading text-xs tracking-[0.15em] text-muted-foreground mb-1 uppercase">
                Logistic Parameters
              </h4>
              <p className="text-xs font-mono text-muted-foreground">
                cover% = {cal.logistic.L.toFixed(1)} + {cal.logistic.k.toFixed(1)} / (1 + exp(
                {(-cal.logistic.b).toFixed(2)} * (score - {cal.logistic.x0.toFixed(2)})))
              </p>
            </div>
          )}

          {cal.bins && cal.bins.length > 0 && (
            <div className="rounded-sm border border-border overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead className="text-xs font-heading tracking-wider">Bin</TableHead>
                    <TableHead className="text-xs font-heading tracking-wider text-right">Predicted</TableHead>
                    <TableHead className="text-xs font-heading tracking-wider text-right">Actual</TableHead>
                    <TableHead className="text-xs font-heading tracking-wider text-right">Gap</TableHead>
                    <TableHead className="text-xs font-heading tracking-wider text-right">Count</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {cal.bins.map((bin) => {
                    const gap = Math.abs(bin.actual - bin.predicted);
                    return (
                      <TableRow key={bin.bin}>
                        <TableCell className="font-mono text-sm">{bin.bin}</TableCell>
                        <TableCell className="font-mono text-sm text-right">
                          {(bin.predicted * 100).toFixed(1)}%
                        </TableCell>
                        <TableCell className="font-mono text-sm text-right">
                          {(bin.actual * 100).toFixed(1)}%
                        </TableCell>
                        <TableCell
                          className={`font-mono text-sm text-right ${
                            gap < 0.05 ? "text-green-400" : gap < 0.10 ? "text-yellow-400" : "text-red-400"
                          }`}
                        >
                          {(gap * 100).toFixed(1)}%
                        </TableCell>
                        <TableCell className="font-mono text-sm text-right">{bin.count}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
