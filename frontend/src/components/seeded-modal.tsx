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
          <p className="sm-note sm-note-soft">
            They’re on today — edit a portion, suggest a food, or correct the
            under-count, then re-tune.
          </p>
        </section>

        {/* the held-out dataset — visible on the previous day */}
        <section className="sm-section">
          <div className="sm-sub mono">Your dataset · {datasetDayLabel}</div>
          <p className="sm-line">
            <b>{result.confirmations}</b> meals you confirmed — logged on the
            previous day and held out as the test set the agent is scored against
            (it never sees them while learning).
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
              See the dataset on {datasetDayLabel} →
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
              then log a meal — the supervisor re-tunes on its own once there&apos;s
              enough signal. It should learn: <i>{p.learns}</i>
            </li>
            <li>
              Watch the <b>agent activity</b> feed on the right, and open{" "}
              <b>⚙ state</b> to see the dataset, the verdict, and what it learned.
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
