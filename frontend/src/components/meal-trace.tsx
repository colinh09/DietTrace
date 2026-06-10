"use client";

// A logged meal's breakdown + correction, as an expanded "mini-dashboard": a
// tinted drawer of floating white tiles — Items (what was logged) → Why these
// portions → [Agent's work | Review] side by side → Why this confidence. The one
// way to correct is the conversational review (plain language, no gram editing).
import { useState } from "react";
import { Check, Globe, History, Pencil, X } from "lucide-react";
import type { ConfidenceAxis, LoggedItem, Nutrient, TraceStep } from "@/lib/api";
import { updateMealItems } from "@/lib/api";
import { MealReview } from "@/components/meal-review";
import type { AgentActivity } from "@/components/agent-decision";
import { macrosOf } from "@/lib/meal";

// The four macro nutrient codes shown (and made editable) in the items table.
const MACRO_CODES = { kcal: "208", protein: "203", carb: "205", fat: "204" } as const;
type MacroVals = { kcal: number; protein: number; carb: number; fat: number };
type EditRow = MacroVals & { grams: number };

// Write a row's edited macro values back onto its item's nutrient list (updating
// the existing code, or appending it if the item lacked one).
function applyEdits(orig: Nutrient[], vals: MacroVals): Nutrient[] {
  const next = orig.map((n) => ({ ...n }));
  (Object.entries(MACRO_CODES) as [keyof MacroVals, string][]).forEach(
    ([key, code]) => {
      const idx = next.findIndex((n) => n.code === code);
      if (idx >= 0) next[idx] = { ...next[idx], amount: vals[key] };
      else next.push({ code, amount: vals[key] } as Nutrient);
    },
  );
  return next;
}

// Meal totals are the per-item nutrients summed by code.
function recomputeTotals(items: LoggedItem[]): Nutrient[] {
  const byCode = new Map<string, Nutrient>();
  items.forEach((it) =>
    it.nutrients.forEach((n) => {
      const ex = byCode.get(n.code);
      byCode.set(n.code, ex ? { ...ex, amount: ex.amount + n.amount } : { ...n });
    }),
  );
  return [...byCode.values()];
}

const intOf = (v: string) => parseInt(v.replace(/[^0-9]/g, "") || "0", 10);

// Each step's rail glyph: a globe for the web fallback, a history mark for a
// recall from memory, and a quiet dot for the ordinary deterministic steps.
export function StepGlyph({ step }: { step?: string }) {
  if (step === "web_search") return <Globe size={11} color="var(--accent)" />;
  if (step === "recall") return <History size={11} color="var(--accent)" />;
  return <span className="step-dot" aria-hidden="true" />;
}

const fmt = new Intl.NumberFormat("en-US");

// Plain-English labels for the raw backend step identifiers shown to users.
// Falls back to prettifying (underscores → spaces) for anything unmapped.
const STEP_LABELS: Record<string, string> = {
  parse_meal: "Read your meal",
  search_nutrition: "Looked up nutrition",
  estimate_portion: "Estimated portions",
  log_entry: "Logged it",
  web_search: "Searched the web",
  recall: "Remembered your preferences",
};

export function stepLabel(step?: string): string {
  if (!step) return "";
  return STEP_LABELS[step] ?? step.replace(/_/g, " ");
}

// Plain-English labels for the eval axes — the raw names are jargon.
const AXIS_LABELS: Record<string, string> = {
  resolution_completeness: "Foods found",
  source_quality: "Trusted data",
  portion_sanity: "Sensible portions",
  calorie_plausibility: "Calories add up",
};

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
  onAgentEvent,
  readOnly = false,
  hasFeedback = false,
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
  onAgentEvent?: AgentActivity;
  // A held-out dataset point: show the breakdown, but not the confirm/correct
  // review (it's already the user's confirmed ground truth).
  readOnly?: boolean;
  // The meal already has a saved correction — show the saved review state.
  hasFeedback?: boolean;
}) {
  const confAxes = axes ?? [];
  const mean =
    confidence != null
      ? confidence
      : confAxes.length
        ? confAxes.reduce((s, a) => s + a.score, 0) / confAxes.length
        : 0;
  const showReview = Boolean(mealText) && !readOnly;
  const cell = (v: number) => fmt.format(Math.round(v));

  // ── Inline item editing — a manual fix to the numbers (grams + macros) that
  // rewrites the log in place. NOT a confirmation/dataset point: it teaches the
  // agent nothing, it just corrects what was recorded. ──
  const canEdit = Boolean(mealId) && !readOnly;
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<EditRow[]>([]);

  const startEdit = () => {
    setDraft(
      perItem.map((it) => {
        const m = macrosOf(it.nutrients);
        return {
          grams: Math.round(it.grams),
          kcal: Math.round(m.kcal),
          protein: Math.round(m.protein),
          carb: Math.round(m.carb),
          fat: Math.round(m.fat),
        };
      }),
    );
    setEditing(true);
  };

  const setField = (i: number, field: keyof EditRow, value: number) =>
    setDraft((d) => d.map((r, j) => (j === i ? { ...r, [field]: value } : r)));

  const saveEdits = async () => {
    if (!mealId || saving) return;
    setSaving(true);
    const items: LoggedItem[] = perItem.map((it, i) => {
      const row = draft[i];
      return { ...it, grams: row.grams, nutrients: applyEdits(it.nutrients, row) };
    });
    try {
      await updateMealItems(mealId, items, recomputeTotals(items));
      setEditing(false);
      onCorrected?.();
    } catch {
      /* leave the editor open so the user can retry */
    } finally {
      setSaving(false);
    }
  };

  // The agent's ordered work, as the dotted-timeline motif.
  const work = (
    <div className="tile">
      <span className="tile-eyebrow">Agent&apos;s work</span>
      <div className="dtrace">
        {trace.map((step, i) => (
          <div className="tnode" key={i}>
            <span
              className={"tnode-dot" + (step.step === "web_search" ? " amber" : "")}
              aria-hidden="true"
            />
            <div className="tnode-key mono">{stepLabel(step.step)}</div>
            <div className="tnode-body">{step.summary}</div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="drawer">
      {/* What was logged — the items table, editable in place (a manual fix,
          not a dataset point). */}
      <div className="tile">
        <div className="tile-head">
          <span className="tile-eyebrow">Items</span>
          {canEdit && !editing && (
            <button
              type="button"
              className="items-edit"
              onClick={startEdit}
              aria-label="edit items"
            >
              <Pencil size={13} aria-hidden="true" />
            </button>
          )}
          {editing && (
            <span className="items-edit-actions">
              <button
                type="button"
                className="items-cancel"
                onClick={() => setEditing(false)}
                disabled={saving}
                aria-label="cancel editing"
              >
                <X size={14} aria-hidden="true" />
              </button>
              <button
                type="button"
                className="items-save"
                onClick={saveEdits}
                disabled={saving}
              >
                <Check size={13} aria-hidden="true" />
                {saving ? "Saving…" : "Save"}
              </button>
            </span>
          )}
        </div>
        <table className="items">
          <thead>
            <tr>
              <th>Food</th>
              <th>Grams</th>
              <th>Kcal</th>
              <th>P</th>
              <th>C</th>
              <th>F</th>
            </tr>
          </thead>
          <tbody>
            {perItem.map((item, i) => {
              const m = macrosOf(item.nutrients);
              const row = draft[i];
              if (editing && row) {
                const inp = (field: keyof EditRow, label: string) => (
                  <input
                    className="item-edit"
                    inputMode="numeric"
                    value={row[field]}
                    aria-label={label}
                    onChange={(e) => setField(i, field, intOf(e.target.value))}
                  />
                );
                return (
                  <tr key={`${item.fdc_id}-${i}`}>
                    <td>
                      <span className="food">{item.description}</span>
                    </td>
                    <td className="tnum">{inp("grams", "grams")} g</td>
                    <td className="tnum">{inp("kcal", "kcal")}</td>
                    <td className="tnum">{inp("protein", "protein")}</td>
                    <td className="tnum">{inp("carb", "carbs")}</td>
                    <td className="tnum">{inp("fat", "fat")}</td>
                  </tr>
                );
              }
              return (
                <tr key={`${item.fdc_id}-${i}`}>
                  <td>
                    <span className="food">{item.description}</span>
                  </td>
                  <td className="tnum">{Math.round(item.grams)} g</td>
                  <td className="tnum">
                    <span className="kcal">{cell(m.kcal)}</span>
                  </td>
                  <td className="tnum">{cell(m.protein)}</td>
                  <td className="tnum">{cell(m.carb)}</td>
                  <td className="tnum">{cell(m.fat)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Why these portions — annotates the grams above. */}
      {perItem.some((it) => it.portion_basis) && (
        <div className="tile">
          <span className="tile-eyebrow">Why these portions</span>
          {perItem.map((it, i) => (
            <div className="why-line" key={`${it.fdc_id}-${i}`}>
              <b>{it.description}</b>
              <span className="why-arrow">
                {" — "}
                {it.portion_basis || `${Math.round(it.grams)} g`}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Agent's work | Review — side by side when there's a review to give. */}
      {showReview ? (
        <div className="tile-row">
          {work}
          <div className="tile review-tile">
            <span className="tile-eyebrow">Review</span>
            <MealReview
              mealId={mealId}
              mealText={mealText as string}
              perItem={perItem}
              totals={totals ?? []}
              hasFeedback={hasFeedback}
              onCorrected={onCorrected}
              onAgentEvent={onAgentEvent}
            />
          </div>
        </div>
      ) : (
        work
      )}

      {/* Why this confidence — the four checks + the average. */}
      {confAxes.length > 0 ? (
        <div className="tile">
          <span className="tile-eyebrow">Why this confidence</span>
          <p className="cb-intro">
            Four automatic checks DietTrace runs on every meal — no human, no
            guessing. The score is their average.
          </p>
          <div className="cb-rows wide">
            {confAxes.map((axis) => {
              const lo = !axis.note.startsWith("✓");
              const pct = Math.round(axis.score * 100);
              return (
                <div className="cb-row" key={axis.name}>
                  <span className="cb-lab">
                    {AXIS_LABELS[axis.name] ?? axis.name.replace(/_/g, " ")}
                  </span>
                  <span className="cb-pct tnum">{pct}%</span>
                  <span className="cb-bar">
                    <span
                      className={"cb-fill" + (lo ? " lo" : "")}
                      style={{ width: `${pct}%` }}
                    />
                  </span>
                  <span className="cb-note">{axis.note.replace(/^[✓⚠]\s*/, "")}</span>
                </div>
              );
            })}
          </div>
          <div className="cb-avg">
            average of {confAxes.length} checks ={" "}
            <b>{Math.round(mean * 100)}% confidence</b>
          </div>
        </div>
      ) : reasons && reasons.length > 0 ? (
        <div className="tile">
          <span className="tile-eyebrow">Why this confidence</span>
          <ul className="conf-reasons-list">
            {reasons.map((reason, i) => (
              <li key={i} className="conf-reason">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
