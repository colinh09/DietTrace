"use client";

// A logged meal's breakdown + correction. The per-item table shows what was
// logged; below it, a single free-form feedback box is the ONE way to correct —
// you tell DietTrace in plain language ("the fries are double what I'd eat") and
// it interprets + applies it (no fiddly gram editing). Behind a quiet toggle:
// the agent's ordered steps, a plain-English recap of WHY it picked these foods
// and portions, and the confidence calculation (each axis → the average).
import { Globe, History } from "lucide-react";
import type { ConfidenceAxis, LoggedItem, Nutrient, TraceStep } from "@/lib/api";
import { MealReview } from "@/components/meal-review";
import { macrosOf } from "@/lib/meal";

// Each step's rail glyph: a globe for the web fallback, a history mark for a
// recall from memory, and a quiet dot for the ordinary deterministic steps.
export function StepGlyph({ step }: { step?: string }) {
  if (step === "web_search") return <Globe size={11} color="var(--accent)" />;
  if (step === "recall") return <History size={11} color="var(--accent)" />;
  return <span className="step-dot" aria-hidden="true" />;
}

function StepLine({ step, isLast }: { step: TraceStep; isLast: boolean }) {
  return (
    <li className="tstep">
      <div className="tstep-rail">
        <span className="tstep-glyph">
          <StepGlyph step={step.step} />
        </span>
        {!isLast && <span className="tstep-line" />}
      </div>
      <div className="tstep-body">
        <div className="tstep-line-btn">
          <span className="tstep-fn mono">{step.step}</span>
          <span className="tstep-arrow">{step.summary}</span>
        </div>
      </div>
    </li>
  );
}

const fmt = new Intl.NumberFormat("en-US");

// Plain-English labels for the eval axes — the raw names are jargon.
const AXIS_LABELS: Record<string, string> = {
  resolution_completeness: "Foods found",
  source_quality: "Trusted data",
  portion_sanity: "Sensible portions",
  calorie_plausibility: "Calories add up",
};

// One read-only item row in the breakdown table.
function ItemRow({ item }: { item: LoggedItem }) {
  const base = macrosOf(item.nutrients);
  const cell = (v: number) => fmt.format(Math.round(v));
  return (
    <div className="item-grid">
      <div className="item-name">
        <span className="item-name-txt">{item.description}</span>
      </div>
      <div className="num mono tnum dim">{Math.round(item.grams)} g</div>
      <div className="num mono tnum">{cell(base.kcal)}</div>
      <div className="num mono tnum dim">{cell(base.protein)}</div>
      <div className="num mono tnum dim">{cell(base.carb)}</div>
      <div className="num mono tnum dim">{cell(base.fat)}</div>
    </div>
  );
}

// "Why these foods & portions" — a plain-English recap per item (body only; the
// card supplies the heading).
function PortionRecapBody({ perItem }: { perItem: LoggedItem[] }) {
  return (
    <ul className="recap-list">
      {perItem.map((it, i) => (
        <li key={`${it.fdc_id}-${i}`} className="recap-row">
          <span className="recap-food">{it.description}</span>
          <span className="recap-why">
            {it.portion_basis || `${Math.round(it.grams)} g`}
          </span>
        </li>
      ))}
    </ul>
  );
}

// "Why this confidence" — the actual calculation: every axis with its score +
// a bar, then the average that produces the headline percentage (body only).
function ConfidenceBody({
  axes,
  confidence,
}: {
  axes: ConfidenceAxis[];
  confidence?: number;
}) {
  const mean =
    confidence != null
      ? confidence
      : axes.reduce((s, a) => s + a.score, 0) / Math.max(1, axes.length);
  return (
    <div className="conf-calc">
      <div className="conf-calc-intro">
        Four automatic checks DietTrace runs on every meal — no human, no
        guessing. The score is their average.
      </div>
      <ul className="conf-calc-list">
        {axes.map((axis) => {
          const pass = axis.note.startsWith("✓");
          return (
            <li key={axis.name} className={"conf-calc-row " + (pass ? "pass" : "warn")}>
              <span className="conf-calc-name">{AXIS_LABELS[axis.name] ?? axis.name.replace(/_/g, " ")}</span>
              <span className="conf-calc-bar">
                <span
                  className="conf-calc-fill"
                  style={{ width: `${Math.round(axis.score * 100)}%` }}
                />
              </span>
              <span className="conf-calc-score mono tnum">
                {Math.round(axis.score * 100)}%
              </span>
              <span className="conf-calc-note">{axis.note.replace(/^[✓⚠]\s*/, "")}</span>
            </li>
          );
        })}
      </ul>
      <div className="conf-calc-total mono">
        average of {axes.length} checks = <b>{Math.round(mean * 100)}% confidence</b>
      </div>
    </div>
  );
}

export function MealTrace({
  trace,
  perItem,
  reasons,
  axes,
  confidence,
  mealText,
  mealId,
  totals,
  onCorrected,
}: {
  trace: TraceStep[];
  perItem: LoggedItem[];
  reasons?: string[];
  // All four confidence sub-scores with ✓/⚠ notes.
  axes?: ConfidenceAxis[];
  // The headline confidence [0,1] (so the breakdown's total matches the chip).
  confidence?: number;
  mealText?: string;
  // The meal's totals — the ground truth recorded when the user confirms it.
  totals?: Nutrient[];
  // The logged meal's store id — passed to the free-form correction so the
  // stored totals are rewritten in-place and /history + /analysis reflect it.
  mealId?: number;
  onCorrected?: () => void;
}) {
  // The expanded meal is one bubble of sub-bubble cards — each part of the
  // agent's accountability in its own card, mirroring the Observability column.
  return (
    <div className="mealtrace">
      {/* What was logged. */}
      <section className="mt-card">
        <div className="mt-card-head mono">items</div>
        <div className="item-grid item-head">
          <div />
          <div className="num">grams</div>
          <div className="num">kcal</div>
          <div className="num">P</div>
          <div className="num">C</div>
          <div className="num">F</div>
        </div>
        {perItem.map((item, i) => (
          <ItemRow key={`${item.fdc_id}-${i}`} item={item} />
        ))}
      </section>

      {/* Review: confirm it (grows the dataset) or correct it (teaches it, XOR). */}
      {mealText && (
        <section className="mt-card">
          <div className="mt-card-head mono">review</div>
          <MealReview
            mealId={mealId}
            mealText={mealText}
            perItem={perItem}
            totals={totals ?? []}
            onCorrected={onCorrected}
          />
        </section>
      )}

      {/* The agent's ordered work. */}
      <section className="mt-card">
        <div className="mt-card-head mono">agent&apos;s work</div>
        <ol className="trace-list">
          {trace.map((step, i) => (
            <StepLine key={i} step={step} isLast={i === trace.length - 1} />
          ))}
        </ol>
      </section>

      {/* Why these foods & portions. */}
      {perItem.some((it) => it.portion_basis) && (
        <section className="mt-card">
          <div className="mt-card-head mono">why these foods &amp; portions</div>
          <PortionRecapBody perItem={perItem} />
        </section>
      )}

      {/* Why this confidence. */}
      {axes && axes.length > 0 ? (
        <section className="mt-card">
          <div className="mt-card-head mono">why this confidence</div>
          <ConfidenceBody axes={axes} confidence={confidence} />
        </section>
      ) : reasons && reasons.length > 0 ? (
        <section className="mt-card">
          <div className="mt-card-head mono">why this confidence</div>
          <ul className="conf-reasons-list">
            {reasons.map((reason, i) => (
              <li key={i} className="conf-reason">
                {reason}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
