"use client";

// The trust report body (no page chrome): mean confidence, where the numbers
// came from, the fraction flagged for review, recent low-confidence meals, and —
// inside the observability modal — the corrections the user has taught the agent.
// Rendered both by the /trust route and inside the observability modal.
import type { FeedbackItem, TrustReport } from "@/lib/api";

const pct = (v: number) => `${Math.round(v * 100)}%`;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="acc-stat">
      <div className="acc-stat-val tnum">{value}</div>
      <div className="acc-stat-label">{label}</div>
    </div>
  );
}

export function TrustView({
  report,
  corrections,
}: {
  report: TrustReport;
  // The user's banked corrections (Input B) — shown only in the modal so the
  // observability surface includes what's been fed into the learning loop.
  corrections?: FeedbackItem[];
}) {
  const sources = Object.entries(report.source_breakdown).sort((a, b) => b[1] - a[1]);
  const sourceTotal = sources.reduce((sum, [, n]) => sum + n, 0);

  return (
    <>
      <section className="acc-hero">
        <h1 className="acc-title" id="obs-modal-title">How much to trust your numbers</h1>
        <p className="acc-sub">
          Every meal you log is scored as it lands — how cleanly it resolved and
          whether the calories reconcile.
          {report.count > 0 &&
            ` Here's how that has held up across your ${report.count} logged meal${
              report.count === 1 ? "" : "s"
            }.`}
        </p>
      </section>

      {report.count === 0 ? (
        <section className="acc-block">
          <p className="acc-sub">
            Nothing logged yet — log a meal and its confidence shows up here.
          </p>
        </section>
      ) : (
        <>
          <section className="acc-stats">
            <Stat label="Mean confidence" value={pct(report.mean_confidence)} />
            <Stat label="Flagged for review" value={pct(report.needs_review_pct)} />
            <Stat label="Meals logged" value={`${report.count}`} />
          </section>

          <section className="acc-block">
            <div className="acc-block-head mono">where the numbers came from</div>
            {sourceTotal > 0 ? (
              <>
                <div className="trust-srcbar">
                  {sources.map(([source, n]) => (
                    <span
                      key={source}
                      className={`trust-srcseg src-${source}`}
                      style={{ width: pct(n / sourceTotal) }}
                      title={`${source}: ${n}`}
                    />
                  ))}
                </div>
                <div className="trust-srckeys">
                  {sources.map(([source, n]) => (
                    <span className="trust-srckey" key={source}>
                      <span className={`trust-dot src-${source}`} />
                      <span className="trust-srcname">{source}</span>
                      <span className="trust-srcnum mono tnum">{pct(n / sourceTotal)}</span>
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <p className="acc-sub">No resolved items yet.</p>
            )}
          </section>

          <section className="acc-block">
            <div className="acc-block-head mono">recent meals worth a second look</div>
            {report.recent_low_confidence.length > 0 ? (
              <ul className="trust-recent">
                {report.recent_low_confidence.map((log, i) => (
                  <li className="trust-recent-row" key={`${log.created_at}-${i}`}>
                    <span className="trust-recent-text">{log.text}</span>
                    <span className="trust-recent-reason">
                      {log.review_reason ?? "low confidence"}
                    </span>
                    <span className="trust-recent-conf mono tnum">{pct(log.confidence)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="acc-sub">
                Nothing flagged — every meal cleared the confidence bar.
              </p>
            )}
          </section>
        </>
      )}

      {corrections && corrections.length > 0 && (
        <section className="acc-block">
          <div className="acc-block-head mono">corrections you&apos;ve taught</div>
          <p className="acc-sub trust-corr-intro">
            Plain-language fixes feeding the learning loop. Re-tune in “Your
            agent” to fold these into a rule — gated so they only ship if they
            actually fit you.
          </p>
          <ul className="trust-corr">
            {corrections.map((c) => (
              <li className="trust-corr-row" key={c.id}>
                <span className="trust-corr-text">“{c.feedback_text}”</span>
                {c.weight > 1 && (
                  <span className="trust-corr-emph mono">emphasized</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
