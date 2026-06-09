"use client";

// An optional "how it works" explainer for new users and judges, in two surfaces
// that share one set of steps (HOW_STEPS):
//   • Tour          — a proactive step-through overlay, one part of the app at a time.
//   • HowItWorksGuide — the same content as a written guide (a tab in the Accuracy modal).
//   • TourPrompt    — a quiet, dismissible nudge that offers the tour to a new user.
// Both surfaces are optional and dismissible; the tour reuses the shared Modal the
// same way the Macros editor reuses the onboarding chat. Plain language throughout.
import { useState } from "react";
import { X } from "lucide-react";
import { Modal } from "@/components/modal";

// One part of the app, explained plainly. `title` doubles as the tour step heading
// and the guide section heading; `body` is the explanation.
export interface HowStep {
  key: string;
  title: string;
  body: string;
}

export const HOW_STEPS: HowStep[] = [
  {
    key: "macros",
    title: "Your day at a glance",
    body: "The band up top tracks the day: calories plus protein, carbs, and fat against the targets you set. It fills in as you log meals, so you always know what's left.",
  },
  {
    key: "log",
    title: "Log food in plain English",
    body: "Type what you ate the way you'd say it — “two eggs and toast.” DietTrace reads it, looks each item up against USDA data, and adds it to your log. Open a meal to see the agent's work, item by item, and why it's confident in the numbers.",
  },
  {
    key: "review",
    title: "Tell it when it's off",
    body: "Each meal asks for a quick check: “Looks right” confirms it, and “Something's off” lets you correct it. A confirm becomes part of your answer key; a correction teaches DietTrace how you actually eat.",
  },
  {
    key: "learning",
    title: "It learns, and proves it stays accurate",
    body: "The side panel is DietTrace working in the open: it banks your corrections and updates itself when it has enough to act on. Every change is checked in Phoenix against your confirmed meals, and only ships if it stays accurate — the Accuracy report shows the before and after.",
  },
];

// The written guide — the same steps as the tour, read top to bottom. Used as the
// "How it works" tab inside the Accuracy modal. The tour button is optional so the
// tab can stand alone (e.g. on a surface that can't launch an overlay).
export function HowItWorksGuide({ onStartTour }: { onStartTour?: () => void }) {
  return (
    <div className="hiw">
      <header className="hiw-head">
        <h1 id="overview-title" className="ov-title">
          How DietTrace works
        </h1>
        <p className="ov-sub">
          A quick walkthrough of each part of the app — log a meal, check the
          numbers, and watch it learn how you eat.
        </p>
      </header>

      <ol className="hiw-list">
        {HOW_STEPS.map((s, i) => (
          <li className="hiw-item" key={s.key}>
            <span className="hiw-num tnum" aria-hidden="true">
              {i + 1}
            </span>
            <div className="hiw-body">
              <h2 className="hiw-title">{s.title}</h2>
              <p className="hiw-text">{s.body}</p>
            </div>
          </li>
        ))}
      </ol>

      {onStartTour && (
        <div className="hiw-foot">
          <button
            type="button"
            className="tg-btn-primary"
            onClick={onStartTour}
          >
            Take the tour
          </button>
        </div>
      )}
    </div>
  );
}

// The interactive tour: one part of the app at a time, Back / Next to move, Done at
// the end. Dismissible at any point (the Modal closes on the ✕, Escape, or a click
// outside) — it never blocks the app.
export function Tour({ onClose }: { onClose: () => void }) {
  const [i, setI] = useState(0);
  const step = HOW_STEPS[i];
  const isLast = i === HOW_STEPS.length - 1;

  return (
    <Modal onClose={onClose} className="modal-narrow" labelledBy="tour-title">
      <div className="tour">
        <span className="tour-count mono">
          {i + 1} / {HOW_STEPS.length}
        </span>
        <h1 id="tour-title" className="tour-title">
          {step.title}
        </h1>
        <p className="tour-text">{step.body}</p>

        <div className="tour-foot">
          {i > 0 && (
            <button
              type="button"
              className="tg-btn-secondary"
              onClick={() => setI((n) => n - 1)}
            >
              Back
            </button>
          )}
          <span className="tour-spacer" />
          {isLast ? (
            <button type="button" className="tg-btn-primary" onClick={onClose}>
              Done
            </button>
          ) : (
            <button
              type="button"
              className="tg-btn-primary"
              onClick={() => setI((n) => n + 1)}
            >
              Next
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}

// A returning visitor who's seen (or dismissed) the nudge shouldn't see it again,
// so the dismissal is a single localStorage flag — same fast-path pattern as the
// onboarding flag.
const PROMPT_KEY = "diettrace_tour_prompt_dismissed";

function promptDismissed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(PROMPT_KEY) === "1";
  } catch {
    return false;
  }
}

function dismissPrompt(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PROMPT_KEY, "1");
  } catch {
    /* storage unavailable — the prompt just won't stay dismissed */
  }
}

// A quiet, dismissible nudge offering the tour. Hides itself once taken or
// dismissed, and stays hidden on the next visit.
export function TourPrompt({ onStartTour }: { onStartTour: () => void }) {
  const [shown, setShown] = useState(() => !promptDismissed());
  if (!shown) return null;

  const start = () => {
    dismissPrompt();
    setShown(false);
    onStartTour();
  };
  const dismiss = () => {
    dismissPrompt();
    setShown(false);
  };

  return (
    <div className="tourp" role="note">
      <span className="tourp-text">
        New here? Take a quick tour of how DietTrace works.
      </span>
      <div className="tourp-actions">
        <button type="button" className="tourp-go" onClick={start}>
          Take the tour
        </button>
        <button
          type="button"
          className="tourp-x"
          aria-label="dismiss"
          onClick={dismiss}
        >
          <X size={15} />
        </button>
      </div>
    </div>
  );
}
