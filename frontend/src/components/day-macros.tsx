// The day-macros band: calories consumed/target as a big number, then protein,
// carb, and fat consumed-vs-target — each under a slim sage progress bar. Wired
// to /analysis (consumed + target) with /goals as the initial-target fallback
//; layout follows  (`.daymacros`).
import type { GoalProgress } from "@/lib/api";

// USDA number codes for the four tracked macros.
// `key` is the one-letter glyph shown in the band; `label` is the spoken name
// for the bar's aria-label (clearer than the verbose USDA names).
const CALORIES = "208";
const MACRO_ORDER: { code: string; key: string; label: string }[] = [
  { code: "203", key: "P", label: "protein" },
  { code: "205", key: "C", label: "carbohydrate" },
  { code: "204", key: "F", label: "fat" },
];

const fmt = new Intl.NumberFormat("en-US");

// Fraction of the target met, clamped to 0–100% (an over-target macro fills
// the bar but never overflows it).
function fillPct(consumed: number, target: number): number {
  if (target <= 0) return 0;
  return Math.max(0, Math.min(100, (consumed / target) * 100));
}

// A slim sage bar whose fill width is the consumed fraction of the target.
function Bar({ consumed, target, label }: { consumed: number; target: number; label: string }) {
  return (
    <div className="bar">
      <div
        className="bar-fill"
        role="progressbar"
        aria-label={label}
        aria-valuenow={Math.round(consumed)}
        aria-valuemin={0}
        aria-valuemax={Math.round(target)}
        style={{ width: `${fillPct(consumed, target)}%` }}
      />
    </div>
  );
}

export function DayMacros({ goals }: { goals: GoalProgress[] }) {
  const byCode = new Map(goals.map((g) => [g.code, g]));
  const cal = byCode.get(CALORIES);
  const calConsumed = cal?.consumed ?? 0;
  const calTarget = cal?.target ?? 0;

  return (
    <section className="daymacros">
      <div className="dm-cal">
        <div className="dm-cal-label">calories</div>
        <div className="dm-cal-val mono tnum">
          {fmt.format(Math.round(calConsumed))}
          <span className="dm-cal-goal"> / {fmt.format(Math.round(calTarget))}</span>
        </div>
        <Bar consumed={calConsumed} target={calTarget} label="calories" />
      </div>
      <div className="dm-macros">
        {MACRO_ORDER.map(({ code, key, label }) => {
          const goal = byCode.get(code);
          const consumed = goal?.consumed ?? 0;
          const target = goal?.target ?? 0;
          return (
            <div className="dm-macro" key={key}>
              <div className="dm-macro-val mono tnum">
                <b>{key}</b>
                {Math.round(consumed)}
                <span className="dm-macro-goal"> / {Math.round(target)} g</span>
              </div>
              <Bar consumed={consumed} target={target} label={label} />
            </div>
          );
        })}
      </div>
    </section>
  );
}
