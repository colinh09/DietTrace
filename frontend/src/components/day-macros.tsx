// The day-macros band: calories as a big ring (consumed vs target with the number
// in the center), then protein, carb, and fat each as a smaller ring. Wired to
// /analysis (consumed + target) with /goals as the initial-target fallback
//.
import type { GoalProgress } from "@/lib/api";
import { Sparkline } from "@/components/sparkline";

// USDA number codes for the four tracked macros.
// Each ring carries its own colour so the four are distinguishable at a glance —
// a muted, palette-friendly take on the common convention (protein green, carbs
// blue, fat gold, calories a warm clay). There's no universal standard.
const CALORIES = "208";
const MACRO_ORDER: { code: string; key: string; label: string; tone: string }[] = [
  { code: "203", key: "P", label: "protein", tone: "var(--macro-protein)" },
  { code: "205", key: "C", label: "carbohydrate", tone: "var(--macro-carb)" },
  { code: "204", key: "F", label: "fat", tone: "var(--macro-fat)" },
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
  tone,
  children,
}: {
  consumed: number;
  target: number;
  size: number;
  stroke: number;
  label: string;
  // The arc colour for this ring (defaults to the sage accent for calories).
  tone?: string;
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
        className="dm-ring"
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
          style={tone ? { stroke: tone } : undefined}
        />
      </svg>
      <div className="ring-center">{children}</div>
    </div>
  );
}

export function DayMacros({
  goals,
  trend,
}: {
  goals: GoalProgress[];
  // The last ~7 days of consumed calories, oldest → newest, for the glance-zone
  // sparkline. Undefined/short until fetched (the sparkline self-hides then).
  trend?: number[];
}) {
  const byCode = new Map(goals.map((g) => [g.code, g]));
  const cal = byCode.get(CALORIES);
  const calConsumed = cal?.consumed ?? 0;
  const calTarget = cal?.target ?? 0;
  // Calories left in the day's budget — the headline of the at-a-glance zone.
  // Past target reads as "over" (the magnitude, never a negative number).
  const remaining = calTarget - calConsumed;
  const over = remaining < 0;

  // The 7-day calorie trend: only meaningful with at least two days of data. The
  // average is over the actual points shown (the mock's "avg 1,866" eyebrow).
  const week = trend ?? [];
  const hasTrend = week.length >= 2;
  const avg = hasTrend
    ? Math.round(week.reduce((sum, c) => sum + c, 0) / week.length)
    : 0;

  return (
    // dm-wrap is a container so the band can stack on its OWN width (it sits in the
    // layout's main column, which goes narrow well before the viewport does).
    <div className="dm-wrap">
      <section className="daymacros">
      <div className="dm-cal">
        <Ring consumed={calConsumed} target={calTarget} size={132} stroke={11} label="calories" tone="var(--macro-cal)">
          <span className="dm-cal-val tnum">{fmt.format(Math.round(calConsumed))}</span>
          <span className="dm-cal-goal tnum">/ {fmt.format(Math.round(calTarget))}</span>
          <span className="dm-cal-label">calories</span>
        </Ring>
      </div>
      <div className="dm-macros">
        {MACRO_ORDER.map(({ code, key, label, tone }) => {
          const goal = byCode.get(code);
          const consumed = goal?.consumed ?? 0;
          const target = goal?.target ?? 0;
          const pct = Math.round(frac(consumed, target) * 100);
          return (
            <div className="dm-bar-row" key={key}>
              <div className="dm-bar-top">
                <span className="dm-bar-name">
                  <span className="dm-bar-key" style={{ color: tone }}>{key}</span>
                  <span className="dm-bar-lab">{label}</span>
                </span>
                <span className="dm-bar-val tnum">
                  <b>{Math.round(consumed)}</b> / {Math.round(target)} g
                </span>
              </div>
              <div
                className="dm-bar"
                role="img"
                aria-label={`${label}: ${Math.round(consumed)} of ${Math.round(target)}`}
              >
                <div
                  className="dm-bar-fill"
                  style={{ width: `${pct}%`, background: tone }}
                />
              </div>
            </div>
          );
        })}
      </div>
      <div className="dm-glance">
        <div className="dm-remain">
          <span className="dm-remain-num tnum">
            {fmt.format(Math.round(Math.abs(remaining)))}
          </span>
          <span className="dm-remain-lab">
            kcal {over ? "over" : "remaining"} today
          </span>
        </div>
        {hasTrend && (
          <div className="dm-spark" aria-label="7-day calorie trend">
            <div className="dm-spark-head">
              <span className="eyebrow">7-day trend</span>
              <span className="dm-spark-avg tnum">avg {fmt.format(avg)}</span>
            </div>
            <Sparkline data={week} target={calTarget} />
          </div>
        )}
      </div>
      </section>
    </div>
  );
}
