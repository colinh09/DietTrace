"use client";

// The confidence chip's styled disclosure. Replaces the giant native `title`
// string with a calm tooltip: the headline score, a one-line "what this is",
// the four automatic checks (each axis → its %), and a "Learn more" link. Shown
// on hover/focus via CSS (`.tip-anchor:hover .tip`), per 
//. The four `axes` already ride along
// on the meal detail; when a meal has none, the chip is rendered
// bare (no tooltip) so older logs degrade gracefully.
import type { ConfidenceAxis } from "@/lib/api";

// Plain-English labels for the eval axes — the raw names are jargon (mirrors the
// breakdown card in meal-trace).
const AXIS_LABELS: Record<string, string> = {
  resolution_completeness: "Foods found",
  source_quality: "Trusted data",
  portion_sanity: "Sensible portions",
  calorie_plausibility: "Calories add up",
};

export function ConfidenceTooltip({
  pct,
  axes,
  children,
}: {
  // The headline confidence percentage shown in the tooltip title.
  pct: number;
  // The confidence chip's level (kept for callers; the value drives the chip).
  level?: string;
  // The four sub-scores. Absent on older logs → render the chip without a tip.
  axes?: ConfidenceAxis[];
  // The chip itself — the tooltip's hover anchor.
  children: React.ReactNode;
}) {
  if (!axes || axes.length === 0) return <>{children}</>;

  return (
    <span className="tip-anchor">
      {children}
      <span className="tip" role="tooltip">
        <span className="tip-title">
          <span>Confidence score</span>
          <span className="pct tnum">{pct}%</span>
        </span>
        <span className="tip-body">
          Average of four automatic checks DietTrace runs on every meal — no
          human, no guessing.
        </span>
        <span className="tip-checks">
          {axes.map((axis) => {
            const low = !axis.note.startsWith("✓");
            return (
              <span className="tip-check" key={axis.name}>
                <span className="lab">
                  {AXIS_LABELS[axis.name] ?? axis.name.replace(/_/g, " ")}
                </span>
                <span className={"v mono" + (low ? " lo" : "")}>
                  {Math.round(axis.score * 100)}%
                </span>
              </span>
            );
          })}
        </span>
        <span className="tip-foot">
          It checks how confidently each food was identified, where the data
          came from, and whether the calories add up — not the exact portion. If
          a gram weight looks off, just tell DietTrace below.{" "}
          <span className="tip-link">Learn more →</span>
        </span>
      </span>
    </span>
  );
}
