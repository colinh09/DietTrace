"use client";

// The "Macro goals" modal. Two views:
//   • Quick edit (default) — edit Calories / Protein / Carb / Fat directly; the
//     macro-derived kcal is shown live and a mismatch with the calorie target is
//     flagged. Fast, no recompute.
//   • Recalculate — the full form (age/sex/… → /macros/plan) for when the user
//     wants DietTrace to recompute everything from their details ("redo setup").
// Save persists via /macros/save.
import { useEffect, useState } from "react";
import { Sparkle } from "lucide-react";
import {
  postMacrosPlan,
  postMacrosSave,
  type GoalProgress,
  type MacroActivity,
  type MacroGoal,
  type MacroPlan,
  type MacroSex,
} from "@/lib/api";
import { getSetup } from "@/lib/setup";

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

const FALLBACK_FORM: FormState = {
  age: "",
  sex: "male",
  height: "",
  weight: "",
  activity: "moderate",
  goal: "maintain",
  ai: true,
  pref: "",
};

function initialForm(): FormState {
  const inputs = getSetup()?.inputs;
  if (!inputs) return FALLBACK_FORM;
  return {
    age: inputs.age != null ? String(inputs.age) : "",
    sex: inputs.sex ?? "male",
    height: inputs.height_cm != null ? String(inputs.height_cm) : "",
    weight: inputs.weight_kg != null ? String(inputs.weight_kg) : "",
    activity: inputs.activity ?? "moderate",
    goal: inputs.goal ?? "maintain",
    ai: true,
    pref: inputs.preference ?? "",
  };
}

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
  goals = [],
}: {
  onClose: () => void;
  onSaved?: () => void;
  // The user's current per-nutrient targets — seeds the quick editor.
  goals?: GoalProgress[];
}) {
  const targetOf = (code: string) =>
    Math.round(goals.find((g) => g.code === code)?.target ?? 0);
  const hasGoals = goals.some((g) => g.target > 0);

  // Default to quick edit when there are targets to edit; otherwise the full form.
  const [view, setView] = useState<"quick" | "recalc">(
    hasGoals ? "quick" : "recalc",
  );

  // ── Quick-edit state ──────────────────────────────────────────────────────
  const [q, setQ] = useState({
    cal: targetOf(ENERGY),
    p: targetOf(PROTEIN),
    c: targetOf(CARB),
    f: targetOf(FAT),
  });
  const [savingQ, setSavingQ] = useState(false);
  const macroKcal = q.p * 4 + q.c * 4 + q.f * 9;
  const diff = macroKcal - q.cal;
  const mismatch = q.cal > 0 && Math.abs(diff) > 25;
  const setQv = (k: keyof typeof q, v: number) => setQ((s) => ({ ...s, [k]: v }));

  const saveQuick = async () => {
    if (savingQ) return;
    setSavingQ(true);
    try {
      await postMacrosSave(
        { [ENERGY]: q.cal, [PROTEIN]: q.p, [CARB]: q.c, [FAT]: q.f },
        null,
        "manual",
      );
      onSaved?.();
      onClose();
    } catch {
      setSavingQ(false);
    }
  };

  // ── Recalculate state ─────────────────────────────────────────────────────
  const [inp, setInp] = useState<FormState>(initialForm);
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
        age: parseInt(inp.age || "30", 10),
        sex: inp.sex,
        height_cm: parseFloat(inp.height || (inp.sex === "female" ? "164" : "178")),
        weight_kg: parseFloat(inp.weight || "70"),
        activity: inp.activity,
        goal: inp.goal,
        preference: inp.pref || null,
        ai_help: inp.ai,
      });
      setPlan(res);
    } catch {
      /* fail-soft — keep the prior plan and let the user retry */
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
  const tdeeStep = plan?.steps?.find(
    (s) => (s as { step?: string }).step === "tdee",
  );
  const tdee =
    tdeeStep && typeof (tdeeStep as { value?: unknown }).value === "number"
      ? (tdeeStep as { value: number }).value
      : kcal;
  const calFill =
    kcal > 0 ? Math.max(4, Math.min(100, (kcal / (tdee || kcal)) * 100)) : 0;

  const ev = plan?.eval;
  const checked = ev
    ? ev.pass
      ? "Plan checked: the numbers add up ✓ · within a safe range ✓"
      : "We nudged the AI's suggestion so the numbers add up and stay in a safe range."
    : null;

  return (
    <div className="tg-scrim" onMouseDown={onClose}>
      <div
        className="tg-card"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Macro goals"
      >
        <button className="tg-x" onClick={onClose} aria-label="close">
          ✕
        </button>

        <div className="tg-eyebrow mono">Macro goals</div>

        {view === "quick" ? (
          <>
            <h2 className="tg-title">Your daily targets</h2>
            <p className="tg-sub">
              Edit any number directly. Your protein, carbs, and fat should add up
              to your calorie target.
            </p>

            <div className="tg-quick">
              <div className="tg-quick-cal">
                <span className="tg-quick-cal-lab">Calories</span>
                <NumEdit
                  value={q.cal}
                  onChange={(v) => setQv("cal", v)}
                  unit="kcal"
                  size="big"
                />
              </div>
              <div className="tg-quick-macros">
                <MacroCol
                  name="Protein"
                  value={q.p}
                  onChange={(v) => setQv("p", v)}
                  fill={(q.p * 4 * 100) / Math.max(1, macroKcal)}
                />
                <MacroCol
                  name="Carb"
                  value={q.c}
                  onChange={(v) => setQv("c", v)}
                  fill={(q.c * 4 * 100) / Math.max(1, macroKcal)}
                />
                <MacroCol
                  name="Fat"
                  value={q.f}
                  onChange={(v) => setQv("f", v)}
                  fill={(q.f * 9 * 100) / Math.max(1, macroKcal)}
                />
              </div>

              <div className={"tg-mismatch" + (mismatch ? " bad" : " ok")}>
                {mismatch ? (
                  <>
                    Your macros add up to <b>{fmt.format(macroKcal)} kcal</b> —{" "}
                    {fmt.format(Math.abs(diff))} {diff > 0 ? "over" : "under"} your{" "}
                    {fmt.format(q.cal)} kcal target.
                  </>
                ) : (
                  <>
                    Your macros add up to <b>{fmt.format(macroKcal)} kcal</b> —
                    matches your calorie target. ✓
                  </>
                )}
              </div>

              <div className="tg-foot">
                <button
                  type="button"
                  className="tg-relink"
                  onClick={() => setView("recalc")}
                >
                  Recalculate from your details →
                </button>
                <button
                  type="button"
                  className="tg-btn-primary"
                  onClick={saveQuick}
                  disabled={savingQ}
                >
                  {savingQ ? "Saving…" : "Save targets"}
                </button>
              </div>
            </div>
          </>
        ) : (
          <>
            <h2 className="tg-title">Recalculate your targets</h2>
            <p className="tg-sub">
              {hasGoals && (
                <button
                  type="button"
                  className="tg-relink back"
                  onClick={() => setView("quick")}
                >
                  ← Back to quick edit
                </button>
              )}
              Recompute everything from your details — adjust anything, then
              recalculate.
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
                      onChange={(e) =>
                        upd("age", e.target.value.replace(/[^0-9]/g, ""))
                      }
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
                      onChange={(e) =>
                        upd("height", e.target.value.replace(/[^0-9]/g, ""))
                      }
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
                      onChange={(e) =>
                        upd("weight", e.target.value.replace(/[^0-9]/g, ""))
                      }
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
                    onChange={(e) =>
                      upd("activity", e.target.value as MacroActivity)
                    }
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
                <Seg
                  value={inp.goal}
                  onChange={(v) => upd("goal", v)}
                  options={GOALS}
                  dots
                />
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
                  {!plan && inp.ai && (
                    <Sparkle size={12} color="var(--on-accent)" />
                  )}
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
          </>
        )}
      </div>
    </div>
  );
}
