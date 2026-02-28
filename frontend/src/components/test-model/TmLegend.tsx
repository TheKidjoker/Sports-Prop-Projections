import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

const definitions: { term: string; def: string }[] = [
  { term: "AUC", def: "Area Under ROC Curve — model discrimination (0.5 = coin flip, 1.0 = perfect)" },
  { term: "Accuracy", def: "% of qualified predictions that covered the spread" },
  { term: "ROI", def: "Return on Investment — net profit per unit wagered assuming -110 odds" },
  { term: "CLV", def: "Closing Line Value — spread movement in your favor after you'd have bet" },
  { term: "Brier Score", def: "Calibration metric — lower is better (0 = perfect, 0.25 = coin flip)" },
  { term: "ECE", def: "Expected Calibration Error — avg gap between predicted and actual probabilities" },
  { term: "Walk-Forward", def: "Out-of-sample validation: train on past data, test on future data, repeat" },
  { term: "EV Model", def: "Expected Value logistic regression model replacing heuristic scoring" },
  { term: "Rules Replay", def: "Backtests production game_scanner scoring against historical outcomes" },
  { term: "Factor Lift", def: "Accuracy improvement when a scoring factor fires vs when it doesn't" },
  { term: "VIF", def: "Variance Inflation Factor — detects multicollinearity (>5 = concern)" },
  { term: "Isotonic", def: "Non-parametric calibration — maps scores to probabilities monotonically" },
  { term: "Logistic Cal.", def: "4-param logistic calibration fit: L + k / (1 + exp(-b*(x-x0)))" },
  { term: "Wilson CI", def: "Wilson score confidence interval — accounts for small sample sizes" },
  { term: "STRONG PLAY", def: "Highest confidence tier — historically 70%+ accuracy" },
  { term: "LEAN", def: "Minimum confidence tier — historically 53-60% accuracy" },
  { term: "Slot Type", def: "Vegas or Public classification based on day, time, and slate size" },
  { term: "Confirmation Score", def: "Sum of all scoring factors — higher = more confluence" },
];

export function TmLegend() {
  const [open, setOpen] = useState(false);

  return (
    <div className="card-surface rounded-sm">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2 text-xs font-heading tracking-wider text-muted-foreground hover:text-foreground transition-colors"
      >
        <span>TERMINOLOGY</span>
        {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
      </button>
      {open && (
        <div className="px-4 pb-3 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1.5">
          {definitions.map((d) => (
            <div key={d.term} className="flex gap-2 text-xs">
              <span className="font-mono text-primary whitespace-nowrap">{d.term}:</span>
              <span className="text-muted-foreground">{d.def}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
