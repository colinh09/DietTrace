"use client";

// The user-triggered "re-tune & re-test" control. Once you've taught the
// agent a few corrections, this offers to re-run it on your own corrected meals —
// base agent vs. agent-with-your-memory — and shows the before/after accuracy. The
// user pulls the trigger (a judge wants to watch it happen), so the cost + the
// ~live wait only happen on demand.
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { retune, type RetuneResult } from "@/lib/api";

const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export function RetunePanel({ corrections }: { corrections: number }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<RetuneResult | null>(null);
  const [error, setError] = useState(false);

  if (corrections < 1) return null;

  async function run() {
    setBusy(true);
    setError(false);
    try {
      setResult(await retune());
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="retune">
      <div className="retune-row">
        <span className="retune-lead">
          <Sparkles size={14} color="var(--accent)" />
          You&apos;ve taught DietTrace{" "}
          <b>
            {corrections} correction{corrections === 1 ? "" : "s"}
          </b>
          .
        </span>
        <button type="button" className="retune-btn mono" onClick={run} disabled={busy}>
          {busy ? "re-testing…" : "re-tune & re-test"}
        </button>
      </div>

      {busy && (
        <div className="retune-note mono">
          running your agent on your corrected meals, with and without what it
          learned…
        </div>
      )}

      {result && !busy && (
        result.cases === 0 ? (
          <div className="retune-note mono">No corrected meals to test yet.</div>
        ) : (
          <div className="retune-result">
            <div className="retune-scores">
              <span className="retune-score">
                <span className="retune-score-label mono">base agent</span>
                <span className="retune-score-val tnum">{pct(result.before)}</span>
              </span>
              <span className="retune-arrow">→</span>
              <span className="retune-score up">
                <span className="retune-score-label mono">with your corrections</span>
                <span className="retune-score-val tnum">{pct(result.after)}</span>
              </span>
            </div>
            <div className="retune-caption">
              Calorie accuracy across your {result.cases} corrected meal
              {result.cases === 1 ? "" : "s"}.{" "}
              {result.improved
                ? "Your corrections made it more accurate."
                : "No change this round."}
            </div>
          </div>
        )
      )}

      {error && !busy && (
        <div className="retune-note mono">re-test failed — try again.</div>
      )}
    </section>
  );
}
