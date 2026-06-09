"use client";

// The "How it works" section — a plain-language walkthrough of each part of the
// app, shown as a tab inside the Accuracy modal. Read top to bottom; optional.
import type { JSX } from "react";

interface HowStep {
  key: string;
  title: string;
  body: string;
}

const HOW_STEPS: HowStep[] = [
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
    body: "Each meal asks for a quick check: “Looks right” confirms it, and “Something's off” lets you correct it. A confirm becomes part of your dataset; a correction teaches DietTrace how you actually eat.",
  },
  {
    key: "learning",
    title: "It learns, and proves it stays accurate",
    body: "The side panel is DietTrace working in the open: it banks your corrections and updates itself when it has enough to act on. Every change is checked in Phoenix against your confirmed meals, and only ships if it stays accurate — the numbers above show the before and after.",
  },
];

export function HowItWorksGuide(): JSX.Element {
  return (
    <div className="hiw">
      <header className="hiw-head">
        <h1 className="ov-title">How DietTrace works</h1>
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
    </div>
  );
}
