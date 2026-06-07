"use client";

// The day's logged meals as compact rows. Each row is
// one line: ✦ meal text · time, then kcal · P/C/F inline, a confidence chip, an
// edit affordance, and an expand chevron. Layout follows 
// (`.meals` / `.meal`). Expanding a row reveals the agent's-work trace — its
// ordered steps plus the per-item editable table — from that meal's `/log`
// detail when we have it.
import { useState } from "react";
import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import type { ConfidenceAxis, LoggedItem, Meal, TraceStep } from "@/lib/api";
import { confidenceFromScore, confidenceOf, macrosOf } from "@/lib/meal";
import { formatTime } from "@/lib/date";
import { MealTrace } from "@/components/meal-trace";
import type { AgentActivity } from "@/components/agent-decision";

// The agent's-work detail for a meal, captured from its `/log` response: the
// reconstructed trace steps, the per-item nutrient panels, and the online
// quality eval (`confidence` in [0,1] + `reasons`) the backend reported
//.
export interface MealDetail {
  trace: TraceStep[];
  perItem: LoggedItem[];
  confidence?: number;
  reasons?: string[];
  // All four confidence sub-scores with ✓/⚠ notes.
  axes?: ConfidenceAxis[];
  // Set when the backend's online-eval confidence fell below the review
  // threshold: the row offers a calm "review?" affordance into
  // the correction editor, with `reviewReason` the single top reason to glance at.
  needsReview?: boolean;
  reviewReason?: string | null;
}

const fmt = new Intl.NumberFormat("en-US");

// Build the expandable breakdown from a meal read back from /history (which
// carries its own per_item + trace), so meals not logged this session — seeded
// dataset points and the simulated previous day — still expand to a full table.
function detailFromMeal(meal: Meal): MealDetail | undefined {
  if (!meal.per_item?.length && !meal.trace?.length) return undefined;
  return {
    trace: meal.trace ?? [],
    perItem: meal.per_item ?? [],
    confidence: meal.confidence,
    reasons: meal.reasons,
    axes: meal.axes,
    needsReview: meal.needs_review,
    reviewReason: meal.review_reason,
  };
}

// One compact meal row. Owns only its open/closed state; the expanded trace is
// filled in 9.7, so for now the chevron toggles an empty region.
function MealRow({
  meal,
  detail,
  onEdit,
  onCorrected,
  onAgentEvent,
}: {
  meal: Meal;
  detail?: MealDetail;
  onEdit?: (meal: Meal) => void;
  onCorrected?: () => void;
  onAgentEvent?: AgentActivity;
}) {
  // A meal is collapsed to a one-line summary by default; clicking the row
  // expands its full breakdown (every accountability card, incl. confidence).
  const [expanded, setExpanded] = useState(false);
  const macros = macrosOf(meal.totals);
  // A held-out confirmed meal mirrored as a visible row: it's the user's asserted
  // ground truth (the gate's test set), not an agent estimate — so it shows a
  // "dataset point" badge instead of a confidence chip, and expands to explain
  // its role rather than a per-item trace (the observability-everywhere rule).
  const isDataset = meal.dataset_point === true;
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
    "not verify the portion, so if a gram weight looks off, just tell DietTrace " +
    "below in plain words and it'll fix it.";

  // Expand the breakdown — used by the review flag so a flagged meal goes one
  // click from "!" to its cards (incl. the "why this confidence" card).
  const openForReview = (e: React.MouseEvent) => {
    e.stopPropagation();
    setExpanded(true);
  };

  return (
    <li className={"meal" + (expanded ? " open" : "")}>
      <div
        className="meal-head"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={() => setExpanded((s) => !s)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((s) => !s);
          }
        }}
      >
        <span className="meal-caret" aria-hidden="true">
          {expanded ? <ChevronDown size={19} /> : <ChevronRight size={19} />}
        </span>
        <span className="meal-main">
          <span className="meal-title-row">
            <span className="meal-text">{meal.text}</span>
            {needsReview && !isDataset && (
              <button
                type="button"
                className="meal-review-flag"
                data-tip="Show me why this was flagged"
                aria-label="Show me why this was flagged"
                onClick={openForReview}
              >
                !
              </button>
            )}
          </span>
          <span className="meal-time mono">
            {isDataset ? "your confirmed intake" : formatTime(meal.created_at)}
          </span>
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
          {/* A dataset point keeps its confidence chip — the badge is an extra
              tag alongside it, not a replacement. */}
          {isDataset && (
            <span
              className="dataset-badge"
              title="A meal you confirmed — held out as ground truth to test the agent. It never sees this while learning; it's only scored against it."
            >
              <span className="dataset-badge-dot" aria-hidden="true" />
              dataset point
            </span>
          )}
          <span className={"conf-chip " + chip} title={confTitle}>
            <span className="conf-dot" aria-hidden="true" />
            <span className="conf-label">{conf.level}</span>
            <span className="conf-pct tnum"> · {conf.pct}%</span>
          </span>
          <button
            type="button"
            className="meal-edit"
            aria-label="remove meal"
            title="Remove this meal"
            onClick={(e) => {
              e.stopPropagation();
              onEdit?.(meal);
            }}
          >
            <Trash2 size={14} aria-hidden="true" />
          </button>
        </span>
      </div>
      {expanded && (
        <div className="meal-detail">
          {isDataset && (
            <div className="dataset-explain">
              <b>Held-out ground truth.</b> This is a meal you confirmed, at your
              true intake. Every re-tune re-scores the agent against it to prove a
              learned change actually fits you — but it’s never used to teach the
              agent, so the test stays honest.
            </div>
          )}
          {detail ? (
            <MealTrace
              trace={detail.trace}
              perItem={detail.perItem}
              reasons={detail.reasons}
              axes={detail.axes}
              confidence={detail.confidence}
              mealText={meal.text}
              mealId={meal.id}
              totals={meal.totals}
              onCorrected={onCorrected}
              onAgentEvent={onAgentEvent}
              readOnly={isDataset}
            />
          ) : (
            !isDataset && (
              <div className="meal-detail-empty">
                No breakdown for this meal — log it again to see the per-item table.
              </div>
            )
          )}
        </div>
      )}
    </li>
  );
}

export function MealList({
  meals,
  heading = "Logged",
  detailsById,
  onEdit,
  onCorrected,
  onAgentEvent,
}: {
  meals: Meal[];
  heading?: string;
  detailsById?: Record<number, MealDetail>;
  onEdit?: (meal: Meal) => void;
  onCorrected?: () => void;
  onAgentEvent?: AgentActivity;
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
              detail={detailsById?.[meal.id] ?? detailFromMeal(meal)}
              onEdit={onEdit}
              onCorrected={onCorrected}
              onAgentEvent={onAgentEvent}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
