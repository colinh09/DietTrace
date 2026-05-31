"use client";

// The agent's-work trace behind a meal's expand.
//
// Two calm parts, matching  (`.mealtrace` / trace.jsx):
//   1. the agent's ordered steps — parse_meal → search_nutrition →
//      estimate_portion → log_entry — as one quiet line per step, read straight
//      from the `/log` trace; and
//   2. the per-item table, whose grams are editable and rescale the row's
//      kcal/P/C/F live (the portion is the one number a person actually corrects).
import { useState } from "react";
import { Check, Globe, Sparkle } from "lucide-react";
import {
  submitCorrection,
  type CorrectionResult,
  type LoggedItem,
  type TraceStep,
} from "@/lib/api";
import { macrosOf } from "@/lib/meal";

// The web-search fallback gets its own glyph — it's the moment the agent leaves
// the USDA DB for a grounded web lookup, so it should read distinctly.
export function StepGlyph({ step }: { step?: string }) {
  if (step === "web_search") {
    return <Globe size={11} color="var(--accent)" />;
  }
  return <Sparkle size={11} fill="var(--accent)" color="var(--accent)" />;
}

// One trace step as a calm rail line: the step name, then its summary.
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

// One editable item row. Grams seed from the logged portion; editing them
// rescales the nutrient panel proportionally (the panel is already scaled to the
// logged grams, so the factor is newGrams / loggedGrams).
function ItemRow({ item }: { item: LoggedItem }) {
  const [grams, setGrams] = useState(item.grams);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  const [result, setResult] = useState<CorrectionResult | null>(null);
  const base = macrosOf(item.nutrients);
  const factor = item.grams > 0 ? grams / item.grams : 0;
  const name = item.description;
  const cell = (value: number) => fmt.format(Math.round(value * factor));

  // The portion is the one number a person actually corrects. Once it's been
  // nudged off the logged value, offer to teach it — the correction becomes a
  // ground-truth example in the Arize eval set (the self-supervision loop).
  const changed = grams > 0 && grams !== item.grams && status !== "saved";

  async function save() {
    setStatus("saving");
    try {
      setResult(await submitCorrection(item, grams));
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  return (
    <>
      <div className="item-grid">
        <div className="item-name">
          <span className="item-name-txt">{name}</span>
        </div>
        <div className="num">
          <span className="grams-edit">
            <input
              className="mono tnum"
              type="number"
              min={0}
              max={2000}
              value={grams}
              aria-label={`grams of ${name}`}
              onChange={(e) => setGrams(Number(e.target.value))}
            />
            <span>g</span>
          </span>
        </div>
        <div className="num mono tnum">{cell(base.kcal)}</div>
        <div className="num mono tnum dim">{cell(base.protein)}</div>
        <div className="num mono tnum dim">{cell(base.carb)}</div>
        <div className="num mono tnum dim">{cell(base.fat)}</div>
      </div>

      {changed && (
        <div className="correct-bar">
          <span className="correct-hint">Looks off? Teach DietTrace the right portion.</span>
          <button
            type="button"
            className="correct-btn mono"
            onClick={save}
            disabled={status === "saving"}
          >
            {status === "saving" ? "saving…" : `correct → ${grams} g`}
          </button>
          {status === "error" && (
            <span className="correct-err">couldn&apos;t save — try again</span>
          )}
        </div>
      )}

      {status === "saved" && result && (
        <div className="correct-bar saved">
          <Check size={12} color="var(--accent)" />
          <span className="correct-hint">
            Added to the Arize eval set as ground truth — the next eval run will
            score against it.
          </span>
          <a
            href={result.phoenix_url}
            target="_blank"
            rel="noreferrer"
            className="correct-link mono"
          >
            view in Phoenix →
          </a>
        </div>
      )}
    </>
  );
}

export function MealTrace({
  trace,
  perItem,
}: {
  trace: TraceStep[];
  perItem: LoggedItem[];
}) {
  return (
    <div className="mealtrace">
      <div className="mealtrace-head mono">the agent&apos;s work</div>
      <ol className="trace-list">
        {trace.map((step, i) => (
          <StepLine key={i} step={step} isLast={i === trace.length - 1} />
        ))}
      </ol>
      <div className="exp-pad">
        <div className="item-grid item-head">
          <div>Item</div>
          <div className="num">grams</div>
          <div className="num">kcal</div>
          <div className="num">P</div>
          <div className="num">C</div>
          <div className="num">F</div>
        </div>
        {perItem.map((item, i) => (
          // A meal can carry the same food twice, so pair the id with position.
          <ItemRow key={`${item.fdc_id}-${i}`} item={item} />
        ))}
      </div>
    </div>
  );
}
