"use client";

// The "Macro goals" modal — a quick edit of the daily targets (Calories / Protein /
// Carbs / Fat) with a live add-up check. "Recalculate from your details" hands off
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

const clampInt = (v: number) => Math.max(0, Math.min(99999, Math.round(v)));

// A small vertical chevron stepper (up / down) used by every numeric field.
function Stepper({ onUp, onDown }: { onUp: () => void; onDown: () => void }) {
  return (
    <div className="mt-stepper">
      <button
        type="button"
        className="mt-step"
        onClick={onUp}
        tabIndex={-1}
        aria-label="Increase"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
          <polyline
            points="6 15 12 9 18 15"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <button
        type="button"
        className="mt-step"
        onClick={onDown}
        tabIndex={-1}
        aria-label="Decrease"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none">
          <polyline
            points="6 9 12 15 18 9"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
    </div>
  );
}

const MACROS = [
  { key: "p", name: "Protein", color: "var(--macro-protein)" },
  { key: "c", name: "Carbs", color: "var(--macro-carb)" },
  { key: "f", name: "Fat", color: "var(--macro-fat)" },
] as const;

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

  const kcalOf = { p: q.p * 4, c: q.c * 4, f: q.f * 9 };
  const macroKcal = kcalOf.p + kcalOf.c + kcalOf.f;
  const diff = macroKcal - q.cal;
  const off = q.cal > 0 && Math.abs(diff) > 25;
  const pct = (key: "p" | "c" | "f") =>
    macroKcal ? (kcalOf[key] / macroKcal) * 100 : 0;

  const setQv = (k: keyof typeof q, v: number) =>
    setQ((s) => ({ ...s, [k]: clampInt(v) }));

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
        className="mt-modal"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Macro goals"
      >
        <button className="tg-x" onClick={onClose} aria-label="close">
          ✕
        </button>

        <div className="eyebrow">Macro goals</div>
        <h2 className="mt-title">Your daily targets</h2>
        <p className="mt-help">
          Edit any number directly — your macros power the rest of the app.
        </p>

        <div className="mt-body">
          {/* calories */}
          <div>
            <div className="mt-block-lab">
              <span className="eyebrow">Calories</span>
              <span className="hairline" />
            </div>
            <div className="mt-cal-field">
              <input
                className="mt-cal-input"
                inputMode="numeric"
                value={q.cal}
                size={Math.max(String(q.cal).length, 1)}
                onChange={(e) =>
                  setQv("cal", parseInt(e.target.value.replace(/[^0-9]/g, "") || "0", 10))
                }
                aria-label="Calories"
              />
              <span className="mt-cal-unit">kcal / day</span>
              <Stepper
                onUp={() => setQv("cal", q.cal + 50)}
                onDown={() => setQv("cal", q.cal - 50)}
              />
            </div>
          </div>

          {/* protein / carbs / fat tiles */}
          <div>
            <div className="mt-block-lab">
              <span className="eyebrow">Macronutrients</span>
              <span className="hairline" />
            </div>
            <div className="mt-macros">
              {MACROS.map((m) => (
                <div
                  className="mt-tile"
                  key={m.key}
                  style={{ "--mc": m.color } as React.CSSProperties}
                >
                  <div className="mt-tile-lab">{m.name}</div>
                  <div className="mt-tile-field">
                    <input
                      className="mt-tile-input"
                      inputMode="numeric"
                      value={q[m.key]}
                      size={Math.max(String(q[m.key]).length, 1)}
                      onChange={(e) =>
                        setQv(
                          m.key,
                          parseInt(e.target.value.replace(/[^0-9]/g, "") || "0", 10),
                        )
                      }
                      aria-label={m.name}
                    />
                    <span className="mt-tile-unit">g</span>
                    <Stepper
                      onUp={() => setQv(m.key, q[m.key] + 5)}
                      onDown={() => setQv(m.key, q[m.key] - 5)}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* live macro split */}
          <div className="mt-split">
            <div className="mt-block-lab">
              <span className="eyebrow">Macro split</span>
              <span className="hairline" />
            </div>
            <div
              className="mt-split-bar"
              role="img"
              aria-label="share of calories from each macro"
            >
              {MACROS.map((m) => (
                <span
                  className="mt-seg"
                  key={m.key}
                  style={{ width: `${pct(m.key)}%`, background: m.color }}
                />
              ))}
            </div>
            <div className="mt-split-legend">
              {MACROS.map((m) => (
                <span className="mt-leg" key={m.key}>
                  <span className="mt-leg-dot" style={{ background: m.color }} />
                  {m.name} <b>{Math.round(pct(m.key))}%</b>
                </span>
              ))}
            </div>

            <div className={"mt-check" + (off ? " off" : "")}>
              <svg
                className="mt-check-ic"
                width="15"
                height="15"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                {off ? (
                  <>
                    <path
                      d="M12 3 22 20H2L12 3Z"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinejoin="round"
                    />
                    <line
                      x1="12"
                      y1="10"
                      x2="12"
                      y2="14"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                    <circle cx="12" cy="17" r="1" fill="currentColor" />
                  </>
                ) : (
                  <polyline
                    points="4 12 10 18 20 6"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                )}
              </svg>
              <span>
                Your macros add up to <b>{fmt.format(macroKcal)}</b> of your{" "}
                <b>{fmt.format(q.cal)}</b> kcal target
                {off ? (
                  <>
                    {" "}
                    — <b>{fmt.format(Math.abs(diff))}</b>{" "}
                    {diff > 0 ? "over" : "under"}.
                  </>
                ) : (
                  <> — that matches.</>
                )}
              </span>
            </div>
          </div>
        </div>

        <div className="mt-foot">
          <button
            type="button"
            className="mt-btn mt-btn-ghost"
            onClick={() => onRecalc?.()}
          >
            Recalculate from your details
          </button>
          <button
            type="button"
            className="mt-btn mt-btn-primary"
            onClick={saveQuick}
            disabled={savingQ}
          >
            {savingQ ? "Saving…" : "Save targets"}
          </button>
        </div>
      </div>
    </div>
  );
}
