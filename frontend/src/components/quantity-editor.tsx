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
  onConfirmed: () => void;
  onCancel: () => void;
}) {
  const [grams, setGrams] = useState<number[]>(perItem.map((it) => it.grams));
  const [saving, setSaving] = useState(false);

  const edited = perItem.map((it, i) => rescaleItem(it, grams[i] || 0));
  const totals = sumItemsToTotals(edited);
  const macros = macrosOf(totals);

  const setGram = (i: number, v: number) =>
    setGrams((cur) => cur.map((g, j) => (j === i ? Math.max(0, v) : g)));

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
                  type="number"
                  min={0}
                  value={Math.round(grams[i])}
                  onChange={(e) => setGram(i, Number(e.target.value))}
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
            {saving ? "saving…" : "Save as reference"}
          </button>
        </span>
      </div>
    </div>
  );
}
