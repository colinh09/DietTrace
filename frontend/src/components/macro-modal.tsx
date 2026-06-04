"use client";

// The "Set your targets" modal — the macro editor (design: targets.jsx).
// Calculate calls the REAL backend /macros/plan (deterministic calories + the
// clamped/guarded AI split, scored by the online eval and biased toward the
// user's saved preference); Save persists via /macros/save. Every number stays
// editable. The plan's accountability surface — the eval verdict, whether it was
// personalized, and the safe-range note — is shown inline so the agent's work
// is visible at the point of use.
import { useEffect, useState } from "react";
import { Sparkle } from "lucide-react";
import {
  postMacrosPlan,
  postMacrosSave,
  type MacroActivity,
  type MacroGoal,
  type MacroPlan,
  type MacroSex,
} from "@/lib/api";

const ACTIVITY: { key: MacroActivity; label: string }[] = [
  { key: "sedentary", label: "Sedentary — little exercise" },
  { key: "light", label: "Lightly active — 1–3 days / week" },
  { key: "moderate", label: "Moderately active — 3–5 days / week" },
  { key: "active", label: "Active — 6–7 days / week" },
  { key: "very_active", label: "Very active — hard daily training" },
];
const GOALS: { key: MacroGoal; label: string }[] = [
  { key: "cut", label: "Cut" },
  { key: "maintain", label: "Maintain" },
  { key: "bulk", label: "Bulk" },
];

// USDA codes the band + backend share.
const ENERGY = "208";
const PROTEIN = "203";
const CARB = "205";
const FAT = "204";
const fmt = new Intl.NumberFormat("en-US");

interface FormState {
  age: string;
  sex: MacroSex;
  height: string;
  weight: string;
  activity: MacroActivity;
  goal: MacroGoal;
  ai: boolean;
  pref: string;
}

const DEFAULT_FORM: FormState = {
  age: "31",
  sex: "male",
  height: "178",
  weight: "75",
  activity: "moderate",
  goal: "cut",
  ai: true,
  pref: "keep protein high",
};

function Seg<T extends string>({
  value,
  options,
  onChange,
  dots,
}: {
  value: T;
  options: { key: T; label: string }[];
  onChange: (v: T) => void;
  dots?: boolean;
}) {
  return (
    <div className="tg-seg grow">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          className={"tg-opt" + (value === o.key ? " on" : "")}
          onClick={() => onChange(o.key)}
        >
          {dots && <span className="tg-dot" />}
          {o.label}
        </button>
      ))}
    </div>
  );
}

// Inline dashed-underline number field (the foundation's editable number).
function NumEdit({
  value,
  onChange,
  unit,
  size,
}: {
  value: number;
  onChange: (v: number) => void;
  unit: string;
  size: "big" | "mid";
}) {
  const digits = String(Math.round(value)).length;
  const w = Math.max(size === "big" ? 3 : 2, digits) + 0.4;
  return (
    <span className={"tg-num-edit " + size}>
      <input
        type="text"
        inputMode="numeric"
        value={Math.round(value)}
        style={{ width: w + "ch" }}
        onChange={(e) => {
          const v = e.target.value.replace(/[^0-9]/g, "");
          onChange(v === "" ? 0 : parseInt(v, 10));
        }}
      />
      <span className="tg-num-unit">{unit}</span>
    </span>
  );
}

function MacroCol({
  name,
  value,
  onChange,
  fill,
}: {
  name: string;
  value: number;
  onChange: (v: number) => void;
  fill: number;
}) {
  return (
    <div className="tg-macro">
      <div className="tg-macro-label">{name}</div>
      <div className="tg-macro-val">
        <NumEdit value={value} onChange={onChange} unit="g" size="mid" />
      </div>
      <div className="tg-bar">
        <div className="tg-bar-fill" style={{ width: fill + "%" }} />
      </div>
    </div>
  );
}

export function MacroModal({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved?: () => void;
}) {
  const [inp, setInp] = useState<FormState>(DEFAULT_FORM);
  const [plan, setPlan] = useState<MacroPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const upd = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setInp((s) => ({ ...s, [k]: v }));

  async function calculate() {
    setBusy(true);
    try {
      const res = await postMacrosPlan({
        age: parseInt(inp.age || "0", 10),
        sex: inp.sex,
        height_cm: parseFloat(inp.height || "0"),
        weight_kg: parseFloat(inp.weight || "0"),
        activity: inp.activity,
        goal: inp.goal,
        preference: inp.pref || null,
        ai_help: inp.ai,
      });
      setPlan(res);
    } catch {
      // fail-soft — keep the prior plan (if any) and let the user retry
    } finally {
      setBusy(false);
    }
  }

  const editTarget = (code: string, value: number) =>
    setPlan((p) => (p ? { ...p, targets: { ...p.targets, [code]: value } } : p));

  async function save() {
    if (!plan) return;
    setSaving(true);
    try {
      await postMacrosSave(plan.targets, plan.rationale, plan.source);
      onSaved?.();
      onClose();
    } catch {
      setSaving(false);
    }
  }

  const t = plan?.targets;
  const kcal = t ? t[ENERGY] : 0;
  const pK = t ? t[PROTEIN] * 4 : 0;
  const cK = t ? t[CARB] * 4 : 0;
  const fK = t ? t[FAT] * 9 : 0;
  const macTot = Math.max(1, pK + cK + fK);
  // Show the target against TDEE (from the deterministic steps) so a cut/bulk
  // reads visually; fall back to a full bar when TDEE isn't present.
  const tdeeStep = plan?.steps?.find((s) => (s as { step?: string }).step === "tdee");
  const tdee =
    tdeeStep && typeof (tdeeStep as { value?: unknown }).value === "number"
      ? ((tdeeStep as { value: number }).value)
      : kcal;
  const calFill =
    kcal > 0 ? Math.max(4, Math.min(100, (kcal / (tdee || kcal)) * 100)) : 0;

  const ev = plan?.eval;
  const checked = ev
    ? ev.pass
      ? "Plan checked: consistent ✓ · within safe range ✓"
      : "AI suggestion adjusted to stay consistent + within safe range."
    : null;

  return (
    <div className="tg-scrim" onMouseDown={onClose}>
      <div
        className="tg-card"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Set your targets"
      >
        <button className="tg-x" onClick={onClose} aria-label="close">
          ✕
        </button>

        <div className="tg-eyebrow mono">Macro goals</div>
        <h2 className="tg-title">Set your targets</h2>
        <p className="tg-sub">
          A quick estimate from your body and goal — used only to calculate, not
          stored. Every number stays yours to adjust.
        </p>

        {/* Stage 1 — inputs */}
        <div className="tg-form">
          <div className="tg-grid">
            <label className="tg-f">
              <span className="tg-l">Age</span>
              <div className="tg-input num">
                <input
                  value={inp.age}
                  inputMode="numeric"
                  onChange={(e) => upd("age", e.target.value.replace(/[^0-9]/g, ""))}
                />
                <span className="tg-suf">yr</span>
              </div>
            </label>
            <div className="tg-f">
              <span className="tg-l">Sex</span>
              <Seg
                value={inp.sex}
                onChange={(v) => upd("sex", v)}
                options={[
                  { key: "male", label: "Male" },
                  { key: "female", label: "Female" },
                ]}
              />
            </div>
            <label className="tg-f">
              <span className="tg-l">Height</span>
              <div className="tg-input num">
                <input
                  value={inp.height}
                  inputMode="numeric"
                  onChange={(e) => upd("height", e.target.value.replace(/[^0-9]/g, ""))}
                />
                <span className="tg-suf">cm</span>
              </div>
            </label>
            <label className="tg-f">
              <span className="tg-l">Weight</span>
              <div className="tg-input num">
                <input
                  value={inp.weight}
                  inputMode="numeric"
                  onChange={(e) => upd("weight", e.target.value.replace(/[^0-9]/g, ""))}
                />
                <span className="tg-suf">kg</span>
              </div>
            </label>
          </div>

          <label className="tg-f tg-full">
            <span className="tg-l">Activity</span>
            <div className="tg-select">
              <select
                value={inp.activity}
                onChange={(e) => upd("activity", e.target.value as MacroActivity)}
              >
                {ACTIVITY.map((a) => (
                  <option key={a.key} value={a.key}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>
          </label>

          <div className="tg-f tg-full">
            <span className="tg-l">Goal</span>
            <Seg value={inp.goal} onChange={(v) => upd("goal", v)} options={GOALS} dots />
          </div>

          <div className="tg-f tg-full">
            <div className="tg-l-row">
              <span className="tg-l">
                Preference <span className="opt">optional</span>
              </span>
              <button
                type="button"
                className={"tg-ai" + (inp.ai ? " on" : "")}
                aria-pressed={inp.ai}
                onClick={() => upd("ai", !inp.ai)}
              >
                <span className="tg-ai-glyph">
                  <Sparkle size={12} />
                </span>
                AI help
              </button>
            </div>
            <div className="tg-input">
              <input
                value={inp.pref}
                placeholder="e.g. keep protein high"
                onChange={(e) => upd("pref", e.target.value)}
              />
            </div>
          </div>

          <div className="tg-actions">
            <button
              type="button"
              className={plan ? "tg-recalc" : "tg-btn-primary"}
              onClick={calculate}
              disabled={busy}
            >
              {!plan && inp.ai && <Sparkle size={12} color="#fff" />}
              {busy ? "Calculating…" : plan ? "Recalculate" : "Calculate"}
            </button>
          </div>
        </div>

        {/* Stage 2 — result */}
        <div className="tg-result" data-open={plan ? "true" : "false"}>
          <div className="tg-result-inner">
            <div className="tg-rule" />
            <div className="tg-plan-eyebrow mono">Your daily plan</div>

            <div className="tg-cal">
              <div className="tg-cal-label">Calories</div>
              <div className="tg-cal-val">
                <NumEdit
                  value={kcal}
                  onChange={(v) => editTarget(ENERGY, v)}
                  unit="kcal"
                  size="big"
                />
              </div>
              <div className="tg-bar">
                <div className="tg-bar-fill" style={{ width: calFill + "%" }} />
              </div>
              <div className="tg-cal-ref mono">
                {plan?.source === "ai" ? "AI-personalised" : "formula"} ·{" "}
                <b>{kcal > 0 ? fmt.format(Math.round(kcal)) : ""} kcal/day</b>
              </div>
            </div>

            <div className="tg-macros">
              <MacroCol
                name="Protein"
                value={t ? t[PROTEIN] : 0}
                onChange={(v) => editTarget(PROTEIN, v)}
                fill={(pK / macTot) * 100}
              />
              <MacroCol
                name="Carb"
                value={t ? t[CARB] : 0}
                onChange={(v) => editTarget(CARB, v)}
                fill={(cK / macTot) * 100}
              />
              <MacroCol
                name="Fat"
                value={t ? t[FAT] : 0}
                onChange={(v) => editTarget(FAT, v)}
                fill={(fK / macTot) * 100}
              />
            </div>

            {plan?.rationale && (
              <p className="tg-rationale">
                <span className="tg-r-glyph">
                  <Sparkle size={13} />
                </span>
                {plan.rationale}
              </p>
            )}

            {checked && (
              <div className={"tg-checked" + (ev && !ev.pass ? " amber" : "")}>
                {checked}
                {plan?.personalized && " · tuned to your saved preference"}
              </div>
            )}

            <div className="tg-foot">
              <button type="button" className="tg-btn-quiet" onClick={onClose}>
                Cancel
              </button>
              <button
                type="button"
                className="tg-btn-primary"
                onClick={save}
                disabled={!plan || saving}
              >
                {saving ? "Saving…" : "Save targets"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
