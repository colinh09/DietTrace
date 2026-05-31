"use client";

// The day's logged meals as compact rows. Each row is
// one line: ✦ meal text · time, then kcal · P/C/F inline, a confidence chip, an
// edit affordance, and an expand chevron. Layout follows 
// (`.meals` / `.meal`). Expanding a row reveals the agent's-work trace — that
// content lands in 9.7; this task builds the rows and the collapsed shell.
import { useState } from "react";
import { ChevronDown, Sparkle } from "lucide-react";
import type { Meal } from "@/lib/api";
import { confidenceOf, macrosOf } from "@/lib/meal";
import { formatTime } from "@/lib/date";

const fmt = new Intl.NumberFormat("en-US");

// One compact meal row. Owns only its open/closed state; the expanded trace is
// filled in 9.7, so for now the chevron toggles an empty region.
function MealRow({ meal, onEdit }: { meal: Meal; onEdit?: (meal: Meal) => void }) {
  const [open, setOpen] = useState(false);
  const macros = macrosOf(meal.totals);
  const conf = confidenceOf(macros);
  const chip = conf.level === "High" ? "high" : "med";

  return (
    <li className="meal">
      <div className="meal-head">
        <span className="meal-bullet" aria-hidden="true">
          <Sparkle size={11} fill="var(--accent)" color="var(--accent)" />
        </span>
        <span className="meal-main">
          <span className="meal-text">{meal.text}</span>
          <span className="meal-time mono">{formatTime(meal.created_at)}</span>
        </span>
        <span className="meal-side">
          <span className="meal-macros mono tnum">
            <b>{fmt.format(Math.round(macros.kcal))}</b> kcal
            <span className="mm-sep">·</span>
            <span className="mm-part">P {Math.round(macros.protein)}</span>
            <span className="mm-sep">·</span>
            <span className="mm-part">C {Math.round(macros.carb)}</span>
            <span className="mm-sep">·</span>
            <span className="mm-part">F {Math.round(macros.fat)}</span>
          </span>
          <span className={"conf-chip " + chip}>
            <span className="conf-dot" aria-hidden="true" />
            <span className="conf-label">{conf.level}</span>
            <span className="conf-pct tnum"> · {conf.pct}%</span>
          </span>
          <button
            type="button"
            className="meal-edit"
            aria-label="edit meal"
            onClick={() => onEdit?.(meal)}
          >
            edit
          </button>
          <button
            type="button"
            className="meal-chev"
            aria-label="expand meal details"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            data-open={open ? "true" : "false"}
          >
            <ChevronDown size={16} />
          </button>
        </span>
      </div>
      <div className="meal-exp" data-open={open ? "true" : "false"}>
        {/* The agent's-work trace + editable per-item table land in 9.7. */}
        <div className="meal-exp-inner" />
      </div>
    </li>
  );
}

export function MealList({
  meals,
  heading = "Logged",
  onEdit,
}: {
  meals: Meal[];
  heading?: string;
  onEdit?: (meal: Meal) => void;
}) {
  return (
    <section className="meals">
      <div className="meals-head">
        <h2>{heading}</h2>
        <span className="meals-count mono">
          {meals.length} meal{meals.length === 1 ? "" : "s"}
        </span>
      </div>
      {meals.length === 0 ? (
        <div className="meals-empty">
          Nothing logged on this day. Type a meal above to begin.
        </div>
      ) : (
        <ul className="meals-list">
          {meals.map((meal) => (
            <MealRow key={meal.id} meal={meal} onEdit={onEdit} />
          ))}
        </ul>
      )}
    </section>
  );
}
