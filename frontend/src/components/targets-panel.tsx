// The live "your targets, forming" rail beside the onboarding chat. It previews
// the daily targets client-side (Mifflin-St Jeor + activity factor + goal
// adjustment) so the numbers fill instantly as answers come in — no server call,
// no spend. This is preview only; the authoritative save still runs through
// postMacrosPlan/postMacrosSave on finish, which may personalise further.
"use client";

import { useEffect, useRef, useState } from "react";
import type { JSX } from "react";

// Stored answer values use the app's internal keys (kg, cm, male/female,
// light/moderate/very_active, cut/maintain/bulk).
type Answers = Record<string, string | number>;

const ACT_FACTOR: Record<string, number> = {
  sedentary: 1.2,
  light: 1.375,
  moderate: 1.55,
  active: 1.55,
  very_active: 1.725,
};
const GOAL_ADJ: Record<string, number> = {
  cut: -0.15,
  maintain: 0,
  bulk: 0.1,
};

interface Targets {
  cal: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
}

function computeTargets(a: Answers): Targets | null {
  if (a.weight == null) return null;
  const kg = Number(a.weight);
  const age = Number(a.age) || 30;
  const cm = Number(a.height) || 170;
  const s = a.gender === "male" ? 5 : -161;
  const bmr = 10 * kg + 6.25 * cm - 5 * age + s;
  const activity = typeof a.activity === "string" ? a.activity : "";
  const goal = typeof a.goal === "string" ? a.goal : "";
  const hasAct = !!activity && activity in ACT_FACTOR;
  const cal = hasAct
    ? Math.round((bmr * ACT_FACTOR[activity] * (1 + (GOAL_ADJ[goal] || 0))) / 10) *
      10
    : null;
  const protein = Math.round(
    (activity === "very_active" || goal === "bulk" ? 2.0 : 1.7) * kg,
  );
  const fat = cal ? Math.round((cal * 0.27) / 9) : null;
  const carbs = cal
    ? Math.max(0, Math.round((cal - protein * 4 - fat! * 9) / 4))
    : null;
  return { cal, protein, carbs, fat };
}

// One macro tile that flashes when its value changes.
function Macro({
  name,
  color,
  value,
  target,
}: {
  name: string;
  color: string;
  value: number | null;
  target: number;
}): JSX.Element {
  const [flash, setFlash] = useState(false);
  const prev = useRef(value);
  useEffect(() => {
    if (prev.current !== value && value != null) {
      setFlash(true);
      const t = setTimeout(() => setFlash(false), 650);
      prev.current = value;
      return () => clearTimeout(t);
    }
    prev.current = value;
  }, [value]);
  const pct = value != null ? Math.min(100, (value / target) * 100) : 0;
  return (
    <div className={"ob-macro" + (flash ? " ob-flash" : "")}>
      <div className="ob-macro-top">
        <span className="ob-macro-name" style={{ color }}>
          {name}
        </span>
        <span className="ob-macro-val">
          {value != null ? (
            value + " g"
          ) : (
            <span className="ob-empty">— g</span>
          )}
        </span>
      </div>
      <div className="ob-macro-bar">
        <div
          className="ob-macro-fill"
          style={{ width: pct + "%", background: color }}
        />
      </div>
    </div>
  );
}

export function TargetsPanel({
  answers,
  done,
}: {
  answers: Answers;
  done: boolean;
}): JSX.Element {
  const t = computeTargets(answers);
  const cal = t?.cal ?? null;
  const [calFlash, setCalFlash] = useState(false);
  const prevCal = useRef(cal);
  useEffect(() => {
    if (prevCal.current !== cal && cal != null) {
      setCalFlash(true);
      const id = setTimeout(() => setCalFlash(false), 650);
      prevCal.current = cal;
      return () => clearTimeout(id);
    }
    prevCal.current = cal;
  }, [cal]);

  return (
    <aside className="ob-panel">
      <div className="ob-panel-head">
        <span className="ob-panel-eyebrow">Your targets, forming</span>
      </div>
      <div className={"ob-cal-tile" + (calFlash ? " ob-flash" : "")}>
        <div className="ob-cal-lab">Calories</div>
        <div className="ob-cal-num">
          {cal != null ? (
            <>
              {cal.toLocaleString()}
              <span className="u">kcal</span>
            </>
          ) : (
            <span className="ob-empty">
              —<span className="u">kcal</span>
            </span>
          )}
        </div>
      </div>
      <div className="ob-macros">
        <Macro
          name="Protein"
          color="var(--macro-protein)"
          value={t?.protein ?? null}
          target={220}
        />
        <Macro
          name="Carbs"
          color="var(--macro-carb)"
          value={t?.carbs ?? null}
          target={400}
        />
        <Macro
          name="Fat"
          color="var(--macro-fat)"
          value={t?.fat ?? null}
          target={100}
        />
      </div>
      <p className="ob-panel-note">
        {done
          ? "Locked in — you can fine-tune any number later."
          : "Updates live as you answer. Nothing's saved until you finish."}
      </p>
    </aside>
  );
}
