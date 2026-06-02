"use client";

// The agent's-work trace + the meal-correction editor behind a meal's expand
//. Two calm parts:
//   1. the agent's ordered steps — parse → search/web → portion → log (or a
//      single `recall` step when the meal was served from the user's memory) —
//      one quiet line each, read straight from the `/log` trace; and
//   2. the per-item table. "Something's off?" opens an editor: drop a wrongly
//      added item (the double-count case), nudge a portion, and Save — which
//      teaches the agent (it recalls this meal next time, learns similar ones)
//      and pushes the corrected meal to Arize as ground truth.
import { useState } from "react";
import { Check, Globe, History, Sparkle, X } from "lucide-react";
import {
  correctMeal,
  type CorrectionResult,
  type LoggedItem,
  type TraceStep,
} from "@/lib/api";
import { macrosOf } from "@/lib/meal";

// Each step's rail glyph: a globe for the web fallback, a history mark for a
// recall from memory, the ✦ sparkle otherwise.
export function StepGlyph({ step }: { step?: string }) {
  if (step === "web_search") return <Globe size={11} color="var(--accent)" />;
  if (step === "recall") return <History size={11} color="var(--accent)" />;
  return <Sparkle size={11} fill="var(--accent)" color="var(--accent)" />;
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

// An editable item: its logged values plus the in-editor grams and a removed flag.
interface EditItem extends LoggedItem {
  grams_edit: number;
  removed: boolean;
}

function ItemRow({
  item,
  editing,
  onGrams,
  onToggle,
}: {
  item: EditItem;
  editing: boolean;
  onGrams: (g: number) => void;
  onToggle: () => void;
}) {
  const base = macrosOf(item.nutrients);
  const factor = item.grams > 0 ? item.grams_edit / item.grams : 0;
  const cell = (v: number) => (item.removed ? "—" : fmt.format(Math.round(v * factor)));

  return (
    <div className={"item-grid" + (item.removed ? " removed" : "")}>
      <div className="item-name">
        {editing && (
          <button
            type="button"
            className="item-remove"
            aria-label={item.removed ? `restore ${item.description}` : `remove ${item.description}`}
            onClick={onToggle}
          >
            <X size={13} />
          </button>
        )}
        <span className="item-name-txt">{item.description}</span>
      </div>
      <div className="num">
        {editing && !item.removed ? (
          <span className="grams-edit">
            <input
              className="mono tnum"
              type="number"
              min={0}
              max={2000}
              value={item.grams_edit}
              aria-label={`grams of ${item.description}`}
              onChange={(e) => onGrams(Number(e.target.value))}
            />
            <span>g</span>
          </span>
        ) : (
          <span className="mono tnum dim">{item.removed ? "—" : `${Math.round(item.grams_edit)} g`}</span>
        )}
      </div>
      <div className="num mono tnum">{cell(base.kcal)}</div>
      <div className="num mono tnum dim">{cell(base.protein)}</div>
      <div className="num mono tnum dim">{cell(base.carb)}</div>
      <div className="num mono tnum dim">{cell(base.fat)}</div>
    </div>
  );
}

export function MealTrace({
  trace,
  perItem,
  reasons,
  mealText,
  onCorrected,
}: {
  trace: TraceStep[];
  perItem: LoggedItem[];
  reasons?: string[];
  mealText?: string;
  onCorrected?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [items, setItems] = useState<EditItem[]>(() =>
    perItem.map((it) => ({ ...it, grams_edit: it.grams, removed: false })),
  );
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [result, setResult] = useState<CorrectionResult | null>(null);

  const setGrams = (i: number, g: number) =>
    setItems((cur) => cur.map((it, j) => (j === i ? { ...it, grams_edit: g } : it)));
  const toggle = (i: number) =>
    setItems((cur) => cur.map((it, j) => (j === i ? { ...it, removed: !it.removed } : it)));

  async function save() {
    if (!mealText) return;
    setStatus("saving");
    const kept = items
      .filter((it) => !it.removed)
      .map((it) => ({
        description: it.description,
        fdc_id: it.fdc_id,
        original_grams: it.grams,
        corrected_grams: it.grams_edit,
        nutrients: it.nutrients,
      }));
    try {
      setResult(await correctMeal(mealText, kept));
      setStatus("saved");
      setEditing(false);
      onCorrected?.();
    } catch {
      setStatus("error");
    }
  }

  const canEdit = Boolean(mealText) && status !== "saved";

  return (
    <div className="mealtrace">
      <div className="mealtrace-head mono">the agent&apos;s work</div>
      <ol className="trace-list">
        {trace.map((step, i) => (
          <StepLine key={i} step={step} isLast={i === trace.length - 1} />
        ))}
      </ol>

      {reasons && reasons.length > 0 && (
        <div className="conf-reasons">
          <div className="conf-reasons-head mono">why this confidence</div>
          <ul className="conf-reasons-list">
            {reasons.map((reason, i) => (
              <li key={i} className="conf-reason">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="exp-pad">
        <div className="item-grid item-head">
          <div>Item</div>
          <div className="num">grams</div>
          <div className="num">kcal</div>
          <div className="num">P</div>
          <div className="num">C</div>
          <div className="num">F</div>
        </div>
        {items.map((item, i) => (
          <ItemRow
            key={`${item.fdc_id}-${i}`}
            item={item}
            editing={editing}
            onGrams={(g) => setGrams(i, g)}
            onToggle={() => toggle(i)}
          />
        ))}

        {status === "saved" && result ? (
          <div className="correct-saved">
            <div className="correct-bar saved">
              <Check size={12} color="var(--accent)" />
              <span className="correct-hint">
                Learned — log this meal again and it&apos;ll come back right.
              </span>
            </div>
            <div className="arize-card">
              <span className="arize-card-head mono">
                added to your arize eval set · ground truth ({result.corrections} case
                {result.corrections === 1 ? "" : "s"})
              </span>
              <div className="arize-card-body">
                <span className="arize-truth">{mealText}</span>
                <span className="arize-macros mono tnum">
                  {Math.round(macrosOf(result.totals).kcal)} kcal · P{" "}
                  {Math.round(macrosOf(result.totals).protein)} · C{" "}
                  {Math.round(macrosOf(result.totals).carb)} · F{" "}
                  {Math.round(macrosOf(result.totals).fat)}
                </span>
              </div>
              <span className="arize-card-foot">
                The next re-test scores the agent against this.
              </span>
            </div>
          </div>
        ) : editing ? (
          <div className="correct-bar">
            <span className="correct-hint">
              Remove anything wrong (e.g. a double-counted dish) or fix a portion,
              then teach it.
            </span>
            <button
              type="button"
              className="correct-btn mono"
              onClick={save}
              disabled={status === "saving"}
            >
              {status === "saving" ? "teaching…" : "save correction"}
            </button>
            <button
              type="button"
              className="correct-cancel mono"
              onClick={() => setEditing(false)}
            >
              cancel
            </button>
            {status === "error" && (
              <span className="correct-err">couldn&apos;t save — try again</span>
            )}
          </div>
        ) : (
          canEdit && (
            <div className="correct-bar">
              <button
                type="button"
                className="correct-btn mono"
                onClick={() => setEditing(true)}
              >
                something&apos;s off?
              </button>
            </div>
          )
        )}
      </div>
    </div>
  );
}
