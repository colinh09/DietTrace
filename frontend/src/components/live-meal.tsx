"use client";

// The in-progress meal entry: appears under "Today" the moment you log, then
// shows the agent's work streaming in — one trace line per step as it happens
// (parse → search/portion per food → totals) — before the row settles into a
// normal logged meal. Mirrors the MealTrace step rail so it reads identically.
import type { StreamEvent } from "@/lib/api";
import { StepGlyph, stepLabel } from "@/components/meal-trace";

export interface LiveEntry {
  text: string;
  steps: StreamEvent[];
}

export function LiveMeal({ entry }: { entry: LiveEntry }) {
  const steps = entry.steps;
  return (
    <section className="meals">
      <ul className="meals-list">
        <li className="meal live">
          <div className="meal-head">
            <span className="meal-main">
              <span className="meal-text">{entry.text}</span>
            </span>
            <span className="meal-side">
              <span className="conf-chip working" role="status">
                <span className="conf-dot" aria-hidden="true" />
                <span className="conf-label">working…</span>
              </span>
            </span>
          </div>
          <div className="meal-exp" data-open="true">
            <div className="meal-exp-inner">
              <div className="mealtrace">
                <div className="mealtrace-head mono">Agent&apos;s work</div>
                <ol className="trace-list">
                  {steps.map((s, i) => (
                    <li key={i} className="tstep">
                      <div className="tstep-rail">
                        <span className="tstep-glyph">
                          <StepGlyph step={s.step} />
                        </span>
                        {i < steps.length - 1 && <span className="tstep-line" />}
                      </div>
                      <div className="tstep-body">
                        <div className="tstep-line-btn">
                          <span className="tstep-fn mono">{stepLabel(s.step)}</span>
                          <span className="tstep-arrow">
                            {s.summary}
                            {s.status === "running" && !/[.…]\s*$/.test(s.summary ?? "")
                              ? " …"
                              : ""}
                          </span>
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          </div>
        </li>
      </ul>
    </section>
  );
}
