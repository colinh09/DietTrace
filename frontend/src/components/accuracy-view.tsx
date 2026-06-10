"use client";

// The accuracy report body (no page chrome): the headline hero stats, the
// measured before→after bars (with the Arize Phoenix source tag), and the
// accuracy-over-time trend in its own tile. Rendered both by the /accuracy
// route and inside the observability modal.
import type { AccuracyReport } from "@/lib/api";

const pct = (v: number) => `${Math.round(v * 100)}%`;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="acc-stat">
      <div className="acc-stat-val tnum">{value}</div>
      <div className="acc-stat-label">{label}</div>
    </div>
  );
}

// Macro-coloured lines for the accuracy-over-time trend.
const _LINES = [
  { key: "calorie", label: "calorie", color: "var(--macro-cal)" },
  { key: "macro", label: "macro", color: "var(--macro-protein)" },
  { key: "within_tolerance", label: "within 15%", color: "var(--macro-carb)" },
  { key: "portion", label: "portion", color: "var(--macro-fat)" },
] as const;

// Generic trend chart for any series of score points. A single dotted baseline
// at the bottom is the "trace" motif; each line carries hollow interior dots and
// a larger filled emphasis dot on its final (newest) point.
function TrendChartGeneric<T extends Record<string, number>>({
  trend,
  lines,
  ariaLabel,
}: {
  trend: T[];
  lines: readonly { key: keyof T & string; label: string; color: string }[];
  ariaLabel: string;
}) {
  if (trend.length < 2) return null;
  const W = 360;
  const H = 132;
  const px = 10;
  const py = 14;
  const n = trend.length;
  const x = (i: number) => px + (i * (W - 2 * px)) / (n - 1);
  const y = (v: number) => py + (1 - v) * (H - 2 * py);
  return (
    <div className="acc-chart-tile">
      <svg viewBox={`0 0 ${W} ${H}`} className="acc-trend-svg" role="img"
           aria-label={ariaLabel}>
        {/* dotted baseline — the trace motif */}
        <line className="acc-trend-baseline" x1={px} x2={W - px} y1={y(0)} y2={y(0)} />
        {lines.map((l) => (
          <polyline key={l.key} className="acc-trend-line" style={{ stroke: l.color }}
                    points={trend.map((t, i) => `${x(i)},${y(t[l.key] as number)}`).join(" ")} />
        ))}
        {lines.flatMap((l) =>
          trend.map((t, i) =>
            i === n - 1 ? (
              <circle key={`${l.key}-${i}`} cx={x(i)} cy={y(t[l.key] as number)} r={3.4}
                      style={{ fill: l.color, stroke: "var(--card)" }} strokeWidth={1.6} />
            ) : (
              <circle key={`${l.key}-${i}`} cx={x(i)} cy={y(t[l.key] as number)} r={2.4}
                      style={{ fill: "var(--card)", stroke: l.color }} strokeWidth={1.6} />
            ),
          ),
        )}
      </svg>
      <div className="acc-chart-foot">
        <div className="acc-trend-legend">
          {lines.map((l) => (
            <span key={l.key} className="acc-trend-key">
              <span className="acc-trend-dot" style={{ background: l.color }} />
              {l.label}
            </span>
          ))}
        </div>
        <span className="acc-trend-x mono">experiment 1 → {n}</span>
      </div>
    </div>
  );
}

// The accuracy trend across Phoenix experiments (oldest → newest).
function TrendChart({ trend }: { trend: AccuracyReport["trend"] }) {
  return (
    <TrendChartGeneric
      trend={trend}
      lines={_LINES}
      ariaLabel="nutrition accuracy across experiments"
    />
  );
}

export function AccuracyView({ report }: { report: AccuracyReport }) {
  return (
    <>
      <section className="acc-hero">
        <Stat label="Calorie accuracy" value={pct(report.headline.calorie_accuracy)} />
        <Stat label="Macro accuracy" value={pct(report.headline.macro_accuracy)} />
        <Stat label="Within 15% of actual" value={pct(report.headline.within_tolerance)} />
      </section>

      <section className="acc-block">
        <div className="acc-source-row">
          <span className="acc-eyebrow mono">Before → after tuning</span>
          <hr className="acc-hairline" />
          <span className="phoenix-tag">
            <span className="pdot" />
            Arize Phoenix · {report.experiments ?? 0} experiment
            {report.experiments === 1 ? "" : "s"}
          </span>
        </div>
        <div className="acc-bars">
          {report.metrics.map((m) => (
            <div className="acc-bar-row" key={m.key}>
              <span className="acc-bar-label">{m.label}</span>
              <span className="acc-bar-stack">
                <span className="acc-bar-track">
                  <span className="acc-bar-fill before" style={{ width: pct(m.baseline) }} />
                </span>
                <span className="acc-bar-track">
                  <span className="acc-bar-fill after" style={{ width: pct(m.current) }} />
                </span>
              </span>
              <span className="acc-bar-nums mono tnum">
                <span className="b4">{pct(m.baseline)}</span>
                <span className="arr">→</span>
                <span className="af">{pct(m.current)}</span>
              </span>
            </div>
          ))}
        </div>
      </section>

      {report.trend.length >= 2 && (
        <section className="acc-block">
          <div className="acc-source-row">
            <span className="acc-eyebrow mono">Accuracy over time</span>
            <hr className="acc-hairline" />
          </div>
          <TrendChart trend={report.trend} />
        </section>
      )}
    </>
  );
}
