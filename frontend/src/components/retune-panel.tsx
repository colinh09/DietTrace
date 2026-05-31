"use client";

// The user-triggered "re-tune & re-test" control, made visible. Once
// you've taught the agent corrections, this re-runs it on your own corrected
// meals — base agent vs. agent-with-your-memory — and **streams each case as it's
// scored**, so judges watch the Arize-style eval happen, not just a final number.
// The user pulls the trigger (the cost + ~live wait only happen on demand).
import { useState } from "react";
import { Check, Sparkles } from "lucide-react";
import { retuneStream, type RetuneCase, type RetuneSummary } from "@/lib/api";

const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export function RetunePanel({ corrections }: { corrections: number }) {
  const [busy, setBusy] = useState(false);
  const [cases, setCases] = useState<RetuneCase[]>([]);
  const [summary, setSummary] = useState<RetuneSummary | null>(null);
  const [error, setError] = useState(false);

  if (corrections < 1) return null;

  async function run() {
    setBusy(true);
    setError(false);
    setCases([]);
    setSummary(null);
    try {
      await retuneStream((event) => {
        if (event.type === "case") setCases((cur) => [...cur, event]);
        else setSummary(event);
      });
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

      {(busy || cases.length > 0) && (
        <div className="retune-eval">
          <div className="retune-eval-head mono">
            arize eval · scoring your corrected meals against the agent
            {busy ? " …" : ""}
          </div>
          <ul className="retune-cases">
            {cases.map((c, i) => (
              <li className="retune-case" key={i}>
                <span className="retune-case-check">
                  <Check size={11} color="var(--accent)" />
                </span>
                <span className="retune-case-text">{c.text}</span>
                <span className="retune-case-truth mono tnum">
                  {c.expected_calories} kcal
                </span>
                <span className="retune-case-scores mono tnum">
                  {pct(c.before)} <span className="retune-arrow">→</span>{" "}
                  <b className={c.after >= c.before ? "up" : ""}>{pct(c.after)}</b>
                </span>
              </li>
            ))}
            {busy && (
              <li className="retune-case pending mono">
                running the agent on the next meal…
              </li>
            )}
          </ul>
        </div>
      )}

      {summary && !busy && summary.cases > 0 && (
        <div className="retune-result">
          <div className="retune-scores">
            <span className="retune-score">
              <span className="retune-score-label mono">base agent</span>
              <span className="retune-score-val tnum">{pct(summary.before)}</span>
            </span>
            <span className="retune-arrow big">→</span>
            <span className="retune-score up">
              <span className="retune-score-label mono">with your corrections</span>
              <span className="retune-score-val tnum">{pct(summary.after)}</span>
            </span>
          </div>
          <div className="retune-caption">
            Mean calorie accuracy across your {summary.cases} corrected meal
            {summary.cases === 1 ? "" : "s"}.{" "}
            {summary.improved
              ? "Your corrections made it more accurate."
              : "No change this round."}
          </div>
        </div>
      )}

      {error && !busy && (
        <div className="retune-note mono">re-test failed — try again.</div>
      )}
    </section>
  );
}
