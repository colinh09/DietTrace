"use client";

// The "See it in action" explainer. After /demo/seed runs, this pops up
// and says — in plain words — exactly what was loaded: which persona, today's
// playground meals (incl. the on-screen under-count to correct), and the
// learning state, including the held-out dataset which is now visible as badged
// rows on the previous day (the observability-everywhere rule — nothing hidden).
// It doubles as the persona loader: the switcher at the top re-seeds in place.
import { DEMO_PERSONAS, type SeedDemoResult } from "@/lib/api";
import { Modal } from "@/components/modal";
import { formatHeaderDate, fromISODate } from "@/lib/date";

export function SeededModal({
  result,
  busy,
  onReseed,
  onViewDataset,
  onClose,
}: {
  result: SeedDemoResult;
  busy: boolean;
  onReseed: (persona: string) => void;
  // Jump the page to the previous day, where the dataset-point rows live.
  onViewDataset?: (iso: string) => void;
  onClose: () => void;
}) {
  const p = result.persona;
  const datasetDayLabel = formatHeaderDate(fromISODate(result.dataset_date));

  return (
    <Modal onClose={onClose} labelledBy="seeded-title">
      <div className="sm">
        <header className="sm-head">
          <span className="sm-eyebrow mono">Loaded a demo</span>
          <h2 id="seeded-title" className="sm-title">
            {p.label}
          </h2>
          <p className="sm-blurb">{p.blurb}</p>
        </header>

        {/* persona loader — switch the whole demo in place */}
        <div className="sm-personas" role="group" aria-label="Choose a persona">
          {DEMO_PERSONAS.map((persona) => (
            <button
              key={persona.key}
              type="button"
              className={"sm-persona" + (persona.key === p.key ? " on" : "")}
              disabled={busy}
              aria-pressed={persona.key === p.key}
              onClick={() => persona.key !== p.key && onReseed(persona.key)}
            >
              <span className="sm-persona-label">{persona.label}</span>
              <span className="sm-persona-blurb">{persona.blurb}</span>
            </button>
          ))}
        </div>

        {/* what's loaded, at a glance */}
        <div className="sm-stats">
          <div className="sm-stat">
            <span className="sm-stat-num">{p.meal_texts.length}</span>
            <span className="sm-stat-lab mono">on today</span>
          </div>
          <div className="sm-stat">
            <span className="sm-stat-num">{result.confirmations}</span>
            <span className="sm-stat-lab mono">confirmed</span>
          </div>
          <div className="sm-stat">
            <span className="sm-stat-num">{result.corrections}</span>
            <span className="sm-stat-lab mono">to learn from</span>
          </div>
        </div>

        {/* today's playground meals */}
        <section className="sm-section">
          <div className="sm-sub mono">On today — your playground</div>
          <ul className="sm-meals">
            {p.meal_texts.map((text, i) => {
              const isHook = text
                .toLowerCase()
                .includes(p.hook_meal.toLowerCase());
              return (
                <li key={i} className={"sm-meal" + (isHook ? " hook" : "")}>
                  <span>{text}</span>
                  {isHook && <span className="sm-flag mono">under-counted</span>}
                </li>
              );
            })}
          </ul>
          <p className="sm-note">{p.hook_note}</p>
        </section>

        {/* the held-out dataset — visible on the previous day */}
        <section className="sm-section">
          <div className="sm-sub mono">Confirmed meals · {datasetDayLabel}</div>
          <p className="sm-line">
            Logged on the previous day and kept aside in your dataset — DietTrace is
            checked against them, but never sees them while learning.
          </p>
          {onViewDataset && (
            <button
              type="button"
              className="sm-link"
              onClick={() => {
                onViewDataset(result.dataset_date);
                onClose();
              }}
            >
              See the confirmed meals on {datasetDayLabel} →
            </button>
          )}
        </section>

        {/* corrections — the rule's source */}
        <section className="sm-section">
          <div className="sm-sub mono">
            {result.corrections} correction{result.corrections === 1 ? "" : "s"} to learn from
          </div>
          <ul className="sm-corrections">
            {p.correction_texts.map((text, i) => (
              <li key={i}>“{text}”</li>
            ))}
          </ul>
        </section>

        {/* what to try */}
        <section className="sm-section sm-try">
          <div className="sm-sub mono">Try it</div>
          <ol className="sm-steps">
            <li>
              Correct the under-counted meal on today (tell it in plain words),
              then log a meal — DietTrace updates itself automatically once
              you&apos;ve corrected enough meals. It should learn: <i>{p.learns}</i>
            </li>
            <li>
              Watch the <b>agent activity</b> feed on the right, and open{" "}
              <b>State</b> (top of the feed) to see what it was tested on, the
              result, and what it learned.
            </li>
          </ol>
        </section>

        <div className="sm-actions">
          <button type="button" className="sm-done" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
    </Modal>
  );
}
