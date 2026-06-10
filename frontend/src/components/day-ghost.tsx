// A static, faint day-view preview (a calorie ring + three macro bars) rendered
// blurred behind the welcome card so the first screen hints at what the app
// looks like. Purely decorative — no live data, no interactivity.
import type { JSX } from "react";

const MACROS: [string, string, number][] = [
  ["Protein", "var(--macro-protein)", 0.38],
  ["Carbs", "var(--macro-carb)", 0.32],
  ["Fat", "var(--macro-fat)", 0.5],
];

export function DayGhost(): JSX.Element {
  return (
    <div className="ob-ghost-card" aria-hidden="true">
      <div className="ob-ghost-row">
        <div className="ob-ghost-ring">
          <span className="ob-ghost-cal">933</span>
          <span className="ob-ghost-callab">CALORIES</span>
        </div>
        <div className="ob-ghost-macros">
          {MACROS.map(([name, color, pct]) => (
            <div className="ob-ghost-macro" key={name}>
              <span className="ob-ghost-macro-name" style={{ color }}>
                {name}
              </span>
              <div className="ob-ghost-macro-bar">
                <div
                  className="ob-ghost-macro-fill"
                  style={{ width: `${pct * 100}%`, background: color }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
