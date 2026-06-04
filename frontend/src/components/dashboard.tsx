"use client";

// The observability dashboard — the right rail beside the day's logging. It
// makes DietTrace's self-supervision loop visible at a glance: how many
// corrections you've banked (your personal ground truth), that count climbing
// over time, the on-demand re-tune that scores base-vs-your-corrections, the
// portions you've taught, and the latest meal's agent trace. Data comes from
// /memory, /feedback/recent (with timestamps), /retune, and the last /log.
import { RetunePanel } from "@/components/retune-panel";
import { TaughtPanel } from "@/components/taught-panel";
import { StepGlyph } from "@/components/meal-trace";
import type { RecentCorrection, TraceStep } from "@/lib/api";

export interface LatestTrace {
  text: string;
  steps: TraceStep[];
}

// Cumulative-corrections sparkline. The recent window is the tail of the user's
// corrections, so the series ends at the true banked total and climbs back from
// there — a monotonic line showing the ground-truth set growing.
function CorrectionsSpark({
  taught,
  total,
}: {
  taught: RecentCorrection[];
  total: number;
}) {
  const points = [...taught]
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .map((c, i) => ({
      t: new Date(c.created_at).getTime(),
      n: total - taught.length + i + 1,
    }));
  if (points.length < 2) return null;

  const W = 224;
  const H = 46;
  const px = 3;
  const py = 5;
  const t0 = points[0].t;
  const tSpan = points[points.length - 1].t - t0 || 1;
  const nMax = points[points.length - 1].n || 1;
  const x = (t: number) => px + ((t - t0) / tSpan) * (W - 2 * px);
  const y = (n: number) => H - py - (n / nMax) * (H - 2 * py);
  const line = points.map((p) => `${x(p.t)},${y(p.n)}`).join(" ");
  const area = `${px},${H - py} ${line} ${W - px},${H - py}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="dash-spark-svg" role="img"
         aria-label={`${total} corrections banked over time`}>
      <polygon className="dash-spark-fill" points={area} />
      <polyline className="dash-spark-line" points={line} />
      <circle className="dash-spark-dot" cx={x(points[points.length - 1].t)}
              cy={y(nMax)} r={2.6} />
    </svg>
  );
}

function LatestTraceCard({ trace }: { trace: LatestTrace }) {
  return (
    <section className="dash-card">
      <div className="dash-card-head mono">latest trace</div>
      <div className="dash-trace-meal">{trace.text}</div>
      <div className="dash-trace-flow">
        {trace.steps.map((s, i) => (
          <span className="dash-trace-step" key={`${s.step}-${i}`}>
            <span className="dash-trace-glyph">
              <StepGlyph step={s.step} />
            </span>
            <span className="dash-trace-fn mono">{s.step}</span>
          </span>
        ))}
      </div>
    </section>
  );
}

export function Dashboard({
  corrections,
  taught,
  latestTrace,
}: {
  corrections: number;
  taught: RecentCorrection[];
  latestTrace: LatestTrace | null;
}) {
  return (
    <aside className="dash" aria-label="Observability dashboard">
      <div className="dash-head">
        <span className="dash-title mono">observability</span>
      </div>

      <section className="dash-card dash-stat-card">
        <div className="dash-stat-num tnum">{corrections}</div>
        <div className="dash-stat-label">
          correction{corrections === 1 ? "" : "s"} banked
          <span className="dash-stat-sub">your ground truth</span>
        </div>
      </section>

      {taught.length >= 2 && (
        <section className="dash-card">
          <div className="dash-card-head mono">corrections over time</div>
          <CorrectionsSpark taught={taught} total={corrections} />
        </section>
      )}

      {corrections < 1 && (
        <section className="dash-card dash-empty">
          Correct a meal&apos;s portion and DietTrace banks it as ground truth —
          then re-tune to watch its accuracy climb.
        </section>
      )}

      <RetunePanel corrections={corrections} />
      <TaughtPanel corrections={taught} />
      {latestTrace && latestTrace.steps.length > 0 && (
        <LatestTraceCard trace={latestTrace} />
      )}
    </aside>
  );
}
