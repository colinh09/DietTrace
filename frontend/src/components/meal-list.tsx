"use client";

// The day's logged meals as compact rows. Each row is
// one line: ✦ meal text · time, then kcal · P/C/F inline, a confidence chip, an
// edit affordance, and an expand chevron. Layout follows 
// (`.meals` / `.meal`). Expanding a row reveals the agent's-work trace — its
// ordered steps plus the per-item editable table — from that meal's `/log`
// detail when we have it.
import { useState } from "react";
import type { LoggedItem, Meal, TraceStep } from "@/lib/api";
import { confidenceFromScore, confidenceOf, macrosOf } from "@/lib/meal";
import { formatTime } from "@/lib/date";
import { MealTrace } from "@/components/meal-trace";

// The agent's-work detail for a meal, captured from its `/log` response: the
// reconstructed trace steps, the per-item nutrient panels, and the online
// quality eval (`confidence` in [0,1] + `reasons`) the backend reported
//.
export interface MealDetail {
  trace: TraceStep[];
  perItem: LoggedItem[];
  confidence?: number;
  reasons?: string[];
  // Set when the backend's online-eval confidence fell below the review
  // threshold: the row offers a calm "review?" affordance into
  // the correction editor, with `reviewReason` the single top reason to glance at.
  needsReview?: boolean;
  reviewReason?: string | null;
}

const fmt = new Intl.NumberFormat("en-US");

// One compact meal row. Owns only its open/closed state; the expanded trace is
// filled in 9.7, so for now the chevron toggles an empty region.
function MealRow({
  meal,
  detail,
  onEdit,
  onCorrected,
}: {
  meal: Meal;
  detail?: MealDetail;
  onEdit?: (meal: Meal) => void;
  onCorrected?: () => void;
}) {
  // Set when the user taps "review?": it opens the editor straight into edit
  // mode (vs. the always-shown read-only breakdown).
  const [reviewMode, setReviewMode] = useState(false);
  const macros = macrosOf(meal.totals);
  // Prefer the backend's real online-eval confidence when we have it (a freshly
  // logged meal carries it in its detail); fall back to the macro-reconciliation
  // heuristic for a meal read back from history without a backend score (12.2).
  const conf =
    detail?.confidence != null
      ? confidenceFromScore(detail.confidence)
      : confidenceOf(macros);
  const chip = conf.level === "High" ? "high" : "med";
  // A low-confidence log the backend flagged: offer a calm review affordance
  // that drops the user into the correction editor.
  const needsReview = detail?.needsReview ?? false;
  // The confidence chip is an automatic quality check, NOT a correctness
  // guarantee — a clean resolution can still carry a guessed portion. The
  // tooltip says so and points at the fix.
  const confTitle =
    `${conf.level} confidence (${conf.pct}%) — DietTrace's automatic quality check: ` +
    "how cleanly it resolved each food, the source, and calorie sanity. It does " +
    "not verify the portion, so if a gram weight looks off, tap “something's off?” " +
    "to correct it.";

  return (
    <li className="meal">
      <div className="meal-head">
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
          <span className={"conf-chip " + chip} title={confTitle}>
            <span className="conf-dot" aria-hidden="true" />
            <span className="conf-label">{conf.level}</span>
            <span className="conf-pct tnum"> · {conf.pct}%</span>
          </span>
          {needsReview && (
            <button
              type="button"
              className="meal-review"
              title={detail?.reviewReason ?? undefined}
              onClick={() => setReviewMode(true)}
            >
              review?
            </button>
          )}
          <button
            type="button"
            className="meal-edit"
            aria-label="remove meal"
            onClick={() => onEdit?.(meal)}
          >
            remove
          </button>
        </span>
      </div>
      <div className="meal-detail">
        {detail ? (
          <MealTrace
            // Remount into edit mode when the user taps "review?" — the breakdown
            // is always mounted, so flipping the key is what re-reads startEditing.
            key={reviewMode ? "edit" : "view"}
            trace={detail.trace}
            perItem={detail.perItem}
            reasons={detail.reasons}
            mealText={meal.text}
            startEditing={reviewMode}
            onCorrected={onCorrected}
          />
        ) : (
          <div className="meal-detail-empty">
            No breakdown for this meal — log it again to see the per-item table.
          </div>
        )}
      </div>
    </li>
  );
}

export function MealList({
  meals,
  heading = "Logged",
  detailsById,
  onEdit,
  onCorrected,
}: {
  meals: Meal[];
  heading?: string;
  detailsById?: Record<number, MealDetail>;
  onEdit?: (meal: Meal) => void;
  onCorrected?: () => void;
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
            <MealRow
              key={meal.id}
              meal={meal}
              detail={detailsById?.[meal.id]}
              onEdit={onEdit}
              onCorrected={onCorrected}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
