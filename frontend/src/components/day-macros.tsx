// The day-macros band: calories as a big ring (consumed vs target with the number
// in the center), then protein, carb, and fat each as a smaller ring. Wired to
// /analysis (consumed + target) with /goals as the initial-target fallback
//.
import type { GoalProgress } from "@/lib/api";

// USDA number codes for the four tracked macros.
const CALORIES = "208";
const MACRO_ORDER: { code: string; key: string; label: string }[] = [
  { code: "203", key: "P", label: "protein" },
  { code: "205", key: "C", label: "carbohydrate" },
  { code: "204", key: "F", label: "fat" },
];

const fmt = new Intl.NumberFormat("en-US");

// Fraction of the target met, clamped to 0–1 (an over-target value fills the ring
// but never wraps past full).
function frac(consumed: number, target: number): number {
  if (target <= 0) return 0;
  return Math.max(0, Math.min(1, consumed / target));
}

// A circular progress ring: a faint full track plus a sage arc for the filled
// fraction, swept clockwise from the top. The center is filled by `children`.
function Ring({
  consumed,
  target,
  size,
  stroke,
  label,
  children,
}: {
  consumed: number;
  target: number;
  size: number;
  stroke: number;
  label: string;
  children: React.ReactNode;
}) {
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const filled = frac(consumed, target);
  const mid = size / 2;
  return (
    <div className="ring-wrap" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="ring"
        role="img"
        aria-label={`${label}: ${Math.round(consumed)} of ${Math.round(target)}`}
      >
        <circle
          className="ring-track"
          cx={mid}
          cy={mid}
          r={r}
          fill="none"
          strokeWidth={stroke}
        />
        <circle
          className="ring-fill"
          cx={mid}
          cy={mid}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - filled)}
          transform={`rotate(-90 ${mid} ${mid})`}
        />
      </svg>
      <div className="ring-center">{children}</div>
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
        <Ring consumed={calConsumed} target={calTarget} size={132} stroke={11} label="calories">
          <span className="dm-cal-val tnum">{fmt.format(Math.round(calConsumed))}</span>
          <span className="dm-cal-goal tnum">/ {fmt.format(Math.round(calTarget))}</span>
          <span className="dm-cal-label">calories</span>
        </Ring>
      </div>
      <div className="dm-macros">
        {MACRO_ORDER.map(({ code, key, label }) => {
          const goal = byCode.get(code);
          const consumed = goal?.consumed ?? 0;
          const target = goal?.target ?? 0;
          return (
            <div className="dm-macro" key={key}>
              <Ring consumed={consumed} target={target} size={84} stroke={8} label={label}>
                <span className="dm-macro-key">{key}</span>
                <span className="dm-macro-val tnum">{Math.round(consumed)}</span>
              </Ring>
              <div className="dm-macro-goal tnum">
                {Math.round(consumed)} / {Math.round(target)} g
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
