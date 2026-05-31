"use client";

// The Arize accuracy page: how DietTrace's estimates are held to account by
// Arize Phoenix — the measured before/after improvement and the self-supervision
// loop (trace → evaluate → detect → improve). Read from GET /accuracy.
import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, Sparkle } from "lucide-react";
import { getAccuracy, type AccuracyReport } from "@/lib/api";

const pct = (v: number) => `${Math.round(v * 100)}%`;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="acc-stat">
      <div className="acc-stat-val tnum">{value}</div>
      <div className="acc-stat-label">{label}</div>
    </div>
  );
}

export default function AccuracyPage() {
  const [report, setReport] = useState<AccuracyReport | null>(null);

  useEffect(() => {
    getAccuracy()
      .then(setReport)
      .catch(() => {});
  }, []);

  return (
    <div className="page">
      <main className="wrap">
        <header className="hdr">
          <Link href="/" className="back-link mono">
            <ChevronLeft size={16} /> today
          </Link>
          <div className="brand">
            <Sparkle size={15} fill="var(--accent)" color="var(--accent)" />
            <span className="brand-name">accuracy</span>
          </div>
        </header>

        {report && (
          <>
            <section className="acc-hero">
              <h1 className="acc-title">How DietTrace stays accurate</h1>
              <p className="acc-sub">
                Every estimate is scored against USDA ground truth on Arize
                Phoenix, and a supervisor agent opens a fix when accuracy slips.
              </p>
            </section>

            <section className="acc-stats">
              <Stat
                label="Calorie accuracy"
                value={pct(report.headline.calorie_accuracy)}
              />
              <Stat
                label="Macro accuracy"
                value={pct(report.headline.macro_accuracy)}
              />
              <Stat
                label="Within ±15%"
                value={pct(report.headline.within_tolerance)}
              />
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
                      <span
                        className="acc-bar-base"
                        style={{ width: pct(m.baseline) }}
                      />
                      <span
                        className="acc-bar-cur"
                        style={{ width: pct(m.current) }}
                      />
                    </span>
                    <span className="acc-bar-nums mono tnum">
                      {pct(m.baseline)} → <b>{pct(m.current)}</b>
                    </span>
                  </div>
                ))}
              </div>
            </section>

            <section className="acc-block">
              <div className="acc-block-head mono">the self-supervision loop</div>
              <ol className="trace-list">
                {report.loop.map((s, i) => (
                  <li className="tstep" key={s.step}>
                    <div className="tstep-rail">
                      <span className="tstep-glyph">
                        <Sparkle
                          size={11}
                          fill="var(--accent)"
                          color="var(--accent)"
                        />
                      </span>
                      {i < report.loop.length - 1 && (
                        <span className="tstep-line" />
                      )}
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

            <section className="acc-foot">
              <span>
                Scored on {report.dataset.cases} cases from{" "}
                {report.dataset.source}.
              </span>
              <a
                href={report.phoenix_url}
                target="_blank"
                rel="noreferrer"
                className="acc-link"
              >
                View on Arize Phoenix →
              </a>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
