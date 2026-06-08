"use client";

// "Close — let me tweak a portion": before confirming a meal as ground truth,
// the user can nudge any item's grams so the reference is accurate. Nutrients +
// the meal total recompute live; saving confirms the EDITED meal (a more accurate
// Input A datapoint) via /confirm.
import { useState } from "react";
import { confirmMeal, type LoggedItem } from "@/lib/api";
import { macrosOf, rescaleItem, sumItemsToTotals } from "@/lib/meal";

const fmt = (n: number) => Math.round(n).toLocaleString("en-US");

export function QuantityEditor({
  mealText,
  perItem,
  onConfirmed,
  onCancel,
}: {
  mealText: string;
  perItem: LoggedItem[];
  // Passes the /confirm response up so the parent can fire the same feed event +
  // history refresh as a direct confirm (otherwise an adjusted meal never reaches
  // the agent feed and never becomes a dataset point).
  onConfirmed: (res: Awaited<ReturnType<typeof confirmMeal>>) => void;
  onCancel: () => void;
}) {
  // Hold the raw input STRING, not a number — a controlled number input keeps a
  // stale leading zero ("011") when the parsed value is unchanged, which React
  // won't re-render away. Controlling the string lets us strip it deterministically.
  const [gramsStr, setGramsStr] = useState<string[]>(
    perItem.map((it) => String(Math.round(it.grams))),
  );
  const [saving, setSaving] = useState(false);
  const grams = gramsStr.map((s) => Number(s) || 0);

  const edited = perItem.map((it, i) => rescaleItem(it, grams[i]));
  const totals = sumItemsToTotals(edited);
  const macros = macrosOf(totals);

  const setGram = (i: number, raw: string) => {
    // digits only; strip leading zeros ("011" → "11") but keep "" and a lone "0".
    const v = raw.replace(/[^0-9]/g, "").replace(/^0+(?=\d)/, "");
    setGramsStr((cur) => cur.map((g, j) => (j === i ? v : g)));
  };

  const save = () => {
    if (saving) return;
    setSaving(true);
    confirmMeal(mealText, edited, totals)
      .then(onConfirmed)
      .catch(() => setSaving(false));
  };

  return (
    <div className="qe">
      <div className="qe-rows">
        {perItem.map((it, i) => {
          const kcal = macrosOf(edited[i].nutrients).kcal;
          return (
            <div className="qe-row" key={`${it.fdc_id}-${i}`}>
              <span className="qe-name">{it.description}</span>
              <span className="qe-input-wrap">
                <input
                  className="qe-input mono tnum"
                  type="text"
                  inputMode="numeric"
                  value={gramsStr[i]}
                  onChange={(e) => setGram(i, e.target.value)}
                  aria-label={`grams of ${it.description}`}
                />
                <span className="qe-unit">g</span>
              </span>
              <span className="qe-kcal mono tnum">{fmt(kcal)} kcal</span>
            </div>
          );
        })}
      </div>
      <div className="qe-foot">
        <span className="qe-total mono tnum">
          <b>{fmt(macros.kcal)}</b> kcal · P {fmt(macros.protein)} · C{" "}
          {fmt(macros.carb)} · F {fmt(macros.fat)}
        </span>
        <span className="qe-actions">
          <button type="button" className="qe-cancel" onClick={onCancel}>
            cancel
          </button>
          <button type="button" className="qe-save" onClick={save} disabled={saving}>
            {saving ? "saving…" : "Save as confirmed"}
          </button>
        </span>
      </div>
    </div>
  );
}
