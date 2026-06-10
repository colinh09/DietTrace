"use client";

// The "See it in action" explainer. After /demo/seed runs, this pops up
// and says — in plain words — exactly what was loaded: which persona, today's
// playground meals (incl. the on-screen under-count to correct), and what's been
// confirmed into Your Dataset. It doubles as the persona loader: the switcher at
// the top re-seeds in place. The "view dataset" link jumps the page to the
// previous day, where the held-out dataset-point rows live.
import { Check } from "lucide-react";
import { DEMO_PERSONAS, type SeedDemoResult } from "@/lib/api";
import { Modal } from "@/components/modal";

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
  const hook = p.hook_meal.toLowerCase();

  return (
    <Modal onClose={onClose} labelledBy="seeded-title" className="dm-modal">
      {/* header */}
      <span className="eyebrow">Loaded a demo</span>
      <h2 id="seeded-title" className="dm-title">
        {p.label}
      </h2>
      <p className="dm-sub">{p.blurb}</p>

      <div className="dm-body">
        {/* persona switcher — re-seed the whole demo in place */}
        <section>
          <div className="dm-sec-head">
            <span className="eyebrow">Pick a persona</span>
            <hr />
          </div>
          <div className="dm-personas" role="group" aria-label="Choose a persona">
            {DEMO_PERSONAS.map((persona) => (
              <button
                key={persona.key}
                type="button"
                className={"dm-persona" + (persona.key === p.key ? " on" : "")}
                disabled={busy}
                aria-pressed={persona.key === p.key}
                onClick={() => persona.key !== p.key && onReseed(persona.key)}
              >
                <span className="dm-persona-name">
                  {persona.label}
                  <Check className="tick" size={14} aria-hidden />
                </span>
                <span className="dm-persona-sub">{persona.blurb}</span>
              </button>
            ))}
          </div>
        </section>

        {/* what's loaded, at a glance */}
        <section>
          <div className="dm-sec-head">
            <span className="eyebrow">What&apos;s loaded</span>
            <hr />
          </div>
          <div className="dm-stats">
            <div className="dm-stat">
              <div className="dm-stat-lab">On today</div>
              <div className="dm-stat-num">{p.meal_texts.length}</div>
              <div className="dm-stat-sub">meals</div>
            </div>
            <div className="dm-stat">
              <div className="dm-stat-lab">Confirmed</div>
              <div className="dm-stat-num">{result.confirmations}</div>
              <div className="dm-stat-sub">in Your Dataset</div>
            </div>
            <div className="dm-stat">
              <div className="dm-stat-lab">To learn</div>
              <div className="dm-stat-num">{result.corrections}</div>
              <div className="dm-stat-sub">under-counted</div>
            </div>
          </div>
          {onViewDataset && (
            <button
              type="button"
              className="dm-link"
              onClick={() => {
                onViewDataset(result.dataset_date);
                onClose();
              }}
            >
              See the confirmed meals on the previous day →
            </button>
          )}
        </section>

        {/* on today — your playground */}
        <section>
          <div className="dm-sec-head">
            <span className="eyebrow">On today · your playground</span>
            <hr />
          </div>
          <p className="dm-cap">
            Edit a portion, log a meal, or fix an under-count — then watch it
            re-tune.
          </p>
          <div className="dm-meals">
            {p.meal_texts.map((text, i) => {
              const under = text.toLowerCase().includes(hook);
              return (
                <div key={i} className="dm-meal">
                  <span className="dm-meal-name">{text}</span>
                  {under && (
                    <span className="chip amber">
                      <span className="chip-dot" />
                      Under-counted
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        {/* try it — short numbered steps */}
        <section>
          <div className="dm-sec-head">
            <span className="eyebrow">Try it</span>
            <hr />
          </div>
          <ol className="dm-steps">
            <li className="dm-step">
              Correct an under-counted meal — tell it in plain words.
            </li>
            <li className="dm-step">
              Log a new meal the way you&apos;d actually say it.
            </li>
            <li className="dm-step">
              Watch it re-tune in the agent activity rail.
            </li>
          </ol>
        </section>
      </div>

      <div className="dm-foot">
        <button type="button" className="dm-btn-primary" onClick={onClose}>
          Got it
        </button>
      </div>
    </Modal>
  );
}
