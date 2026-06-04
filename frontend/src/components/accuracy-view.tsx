"use client";

// The accuracy report body (no page chrome): the headline stats, the measured
// before→after bars, the accuracy-over-time trend, and the self-supervision loop.
// Rendered both by the /accuracy route and inside the observability modal.
import { Sparkle } from "lucide-react";
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

const _LINES = [
  { key: "calorie", label: "calorie", color: "var(--accent-ink)" },
  { key: "macro", label: "macro", color: "var(--accent)" },
  { key: "within_tolerance", label: "±15%", color: "var(--muted-ink)" },
  { key: "portion", label: "portion", color: "var(--faint)" },
] as const;

const _MACRO_LINES = [
  { key: "pass_rate", label: "within range", color: "var(--accent)" },
  { key: "mean_score", label: "consistency", color: "var(--accent-ink)" },
] as const;

// Generic trend chart for any series of score points.
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
    <div className="acc-trend">
      <svg viewBox={`0 0 ${W} ${H}`} className="acc-trend-svg" role="img"
           aria-label={ariaLabel}>
        {[0, 0.5, 1].map((g) => (
          <line key={g} className="acc-trend-grid" x1={px} x2={W - px} y1={y(g)} y2={y(g)} />
        ))}
        {lines.map((l) => (
          <polyline key={l.key} className="acc-trend-line" style={{ stroke: l.color }}
                    points={trend.map((t, i) => `${x(i)},${y(t[l.key] as number)}`).join(" ")} />
        ))}
        {lines.flatMap((l) =>
          trend.map((t, i) => (
            <circle key={`${l.key}-${i}`} cx={x(i)} cy={y(t[l.key] as number)} r={2.4}
                    style={{ fill: l.color }} />
          )),
        )}
      </svg>
      <div className="acc-trend-legend">
        {lines.map((l) => (
          <span key={l.key} className="acc-trend-key">
            <span className="acc-trend-dot" style={{ background: l.color }} />
            {l.label}
          </span>
        ))}
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
        <h1 className="acc-title" id="obs-modal-title">How DietTrace stays accurate</h1>
        <p className="acc-sub">
          Every estimate is scored against USDA ground truth on Arize Phoenix, and a
          supervisor agent opens a fix when accuracy slips.
        </p>
      </section>

      <section className="acc-stats">
        <Stat label="Calorie accuracy" value={pct(report.headline.calorie_accuracy)} />
        <Stat label="Macro accuracy" value={pct(report.headline.macro_accuracy)} />
        <Stat label="Within ±15%" value={pct(report.headline.within_tolerance)} />
      </section>

      <section className="acc-block">
        <div className="acc-block-head mono">
          {report.source === "live"
            ? `live from arize phoenix · ${report.experiments} experiment${
                report.experiments === 1 ? "" : "s"
              }`
            : "measured improvement"}
        </div>
        <div className="acc-bars">
          {report.metrics.map((m) => (
            <div className="acc-bar-row" key={m.key}>
              <span className="acc-bar-label">{m.label}</span>
              <span className="acc-bar-track">
                <span className="acc-bar-base" style={{ width: pct(m.baseline) }} />
                <span className="acc-bar-cur" style={{ width: pct(m.current) }} />
              </span>
              <span className="acc-bar-nums mono tnum">
                {pct(m.baseline)} → <b>{pct(m.current)}</b>
              </span>
            </div>
          ))}
        </div>
      </section>

      {report.trend.length >= 2 && (
        <section className="acc-block">
          <div className="acc-block-head mono">
            accuracy over time · {report.trend.length} experiment
            {report.trend.length === 1 ? "" : "s"}
          </div>
          <TrendChart trend={report.trend} />
        </section>
      )}

      <section className="acc-block">
        <div className="acc-block-head mono">the self-supervision loop</div>
        <ol className="trace-list">
          {report.loop.map((s, i) => (
            <li className="tstep" key={s.step}>
              <div className="tstep-rail">
                <span className="tstep-glyph">
                  <Sparkle size={11} fill="var(--accent)" color="var(--accent)" />
                </span>
                {i < report.loop.length - 1 && <span className="tstep-line" />}
              </div>
              <div className="tstep-body">
                <div className="tstep-line-btn">
                  <span className="tstep-fn mono">{s.step}</span>
                  <span className="tstep-arrow">{s.label}</span>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {report.macros && (
        <section className="acc-block">
          <div className="acc-block-head mono">
            macro planner · {report.macros.dataset.cases} cases
            {report.macros.experiments != null
              ? ` · ${report.macros.experiments} experiment${report.macros.experiments === 1 ? "" : "s"}`
              : ""}
          </div>
          <div className="acc-bars">
            <div className="acc-bar-row">
              <span className="acc-bar-label">Within target range</span>
              <span className="acc-bar-track">
                <span className="acc-bar-cur"
                      style={{ width: pct(report.macros.headline.pass_rate) }} />
              </span>
              <span className="acc-bar-nums mono tnum">
                <b>{pct(report.macros.headline.pass_rate)}</b>
              </span>
            </div>
            <div className="acc-bar-row">
              <span className="acc-bar-label">Atwater consistency</span>
              <span className="acc-bar-track">
                <span className="acc-bar-cur"
                      style={{ width: pct(report.macros.headline.mean_score) }} />
              </span>
              <span className="acc-bar-nums mono tnum">
                <b>{pct(report.macros.headline.mean_score)}</b>
              </span>
            </div>
          </div>
          {report.macros.trend.length >= 2 && (
            <TrendChartGeneric
              trend={report.macros.trend}
              lines={_MACRO_LINES}
              ariaLabel="macro planner accuracy across experiments"
            />
          )}
        </section>
      )}

      <section className="acc-foot">
        <span>
          Scored on {report.dataset.cases} cases from {report.dataset.source}.
        </span>
        <span className="acc-link">
          {report.source === "live"
            ? `Live from Arize Phoenix · ${report.experiments} experiment${
                report.experiments === 1 ? "" : "s"
              }`
            : "Measured on Arize Phoenix"}
        </span>
      </section>
    </>
  );
}
