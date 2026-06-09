"use client";

// The "Macro goals" modal — a quick edit of the daily targets (Calories / Protein /
// Carb / Fat) with a live mismatch check. "Recalculate from your details" hands off
// to the page, which re-runs the onboarding chat to recompute everything from
// scratch (the same conversational setup as first-run / reset).
import { useEffect, useState } from "react";
import { postMacrosSave, type GoalProgress } from "@/lib/api";

// USDA codes the band + backend share.
const ENERGY = "208";
const PROTEIN = "203";
const CARB = "205";
const FAT = "204";
const fmt = new Intl.NumberFormat("en-US");

// Inline editable number as a clear bordered field (the box signals it's editable).
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
}: {
  name: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="tg-macro">
      <div className="tg-macro-label">{name}</div>
      <div className="tg-macro-val">
        <NumEdit value={value} onChange={onChange} unit="g" size="mid" />
      </div>
    </div>
  );
}

export function MacroModal({
  onClose,
  onSaved,
  onRecalc,
  goals = [],
}: {
  onClose: () => void;
  onSaved?: () => void;
  // Re-run the onboarding chat to recompute targets (wired by the page).
  onRecalc?: () => void;
  // The user's current per-nutrient targets — seeds the editor.
  goals?: GoalProgress[];
}) {
  const targetOf = (code: string) =>
    Math.round(goals.find((g) => g.code === code)?.target ?? 0);

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

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

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
        <h2 className="tg-title">Your daily targets</h2>
        <p className="tg-sub">
          Edit any number directly. Your protein, carbs, and fat should add up to
          your calorie target.
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
            <MacroCol name="Protein" value={q.p} onChange={(v) => setQv("p", v)} />
            <MacroCol name="Carb" value={q.c} onChange={(v) => setQv("c", v)} />
            <MacroCol name="Fat" value={q.f} onChange={(v) => setQv("f", v)} />
          </div>

          {macroKcal > 0 && (
            <div className="tg-split-wrap">
              <div
                className="tg-split"
                role="img"
                aria-label="share of calories from each macro"
              >
                <span
                  className="tg-split-seg"
                  style={{
                    width: `${((q.p * 4) / macroKcal) * 100}%`,
                    background: "var(--macro-protein)",
                  }}
                />
                <span
                  className="tg-split-seg"
                  style={{
                    width: `${((q.c * 4) / macroKcal) * 100}%`,
                    background: "var(--macro-carb)",
                  }}
                />
                <span
                  className="tg-split-seg"
                  style={{
                    width: `${((q.f * 9) / macroKcal) * 100}%`,
                    background: "var(--macro-fat)",
                  }}
                />
              </div>
              <div className="tg-split-legend mono">
                <span>
                  <i style={{ background: "var(--macro-protein)" }} />
                  Protein {Math.round(((q.p * 4) / macroKcal) * 100)}%
                </span>
                <span>
                  <i style={{ background: "var(--macro-carb)" }} />
                  Carbs {Math.round(((q.c * 4) / macroKcal) * 100)}%
                </span>
                <span>
                  <i style={{ background: "var(--macro-fat)" }} />
                  Fat {Math.round(((q.f * 9) / macroKcal) * 100)}%
                </span>
              </div>
            </div>
          )}

          <div className={"tg-mismatch" + (mismatch ? " bad" : " ok")}>
            {mismatch ? (
              <>
                Your macros add up to <b>{fmt.format(macroKcal)} kcal</b> —{" "}
                {fmt.format(Math.abs(diff))} {diff > 0 ? "over" : "under"} your{" "}
                {fmt.format(q.cal)} kcal target.
              </>
            ) : (
              <>
                Your macros add up to <b>{fmt.format(macroKcal)} kcal</b> — matches
                your calorie target. ✓
              </>
            )}
          </div>

          <div className="tg-foot">
            {onRecalc && (
              <button
                type="button"
                className="tg-btn-secondary"
                onClick={onRecalc}
              >
                Recalculate from your details
              </button>
            )}
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
      </div>
    </div>
  );
}
