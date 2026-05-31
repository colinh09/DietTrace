// View-model helpers for a logged meal's compact row.
//
// A /history meal carries only its free text and a nutrient panel keyed by USDA
// number codes; these pull the four tracked macros out of that panel and derive
// the row's confidence chip from how well they reconcile to the calorie total.
import type { Nutrient } from "@/lib/api";

// USDA number codes for the macros a meal row surfaces (matches goals.py).
const ENERGY = "208";
const PROTEIN = "203";
const FAT = "204";
const CARB = "205";

// The four macro amounts a row shows, in display order.
export interface MacroSummary {
  kcal: number;
  protein: number;
  carb: number;
  fat: number;
}

// Pull the tracked macros out of a nutrient panel; any macro the panel omits
// reads as zero so the row never shows a blank.
export function macrosOf(totals: Nutrient[]): MacroSummary {
  const byCode = new Map(totals.map((n) => [n.code, n.amount]));
  return {
    kcal: byCode.get(ENERGY) ?? 0,
    protein: byCode.get(PROTEIN) ?? 0,
    carb: byCode.get(CARB) ?? 0,
    fat: byCode.get(FAT) ?? 0,
  };
}

export type ConfidenceLevel = "High" | "Medium";

export interface Confidence {
  level: ConfidenceLevel;
  pct: number;
}

// A row-level confidence estimate for a logged meal, derived from how well its
// macro breakdown reconciles to its calorie total (the Atwater identity
// 4·protein + 4·carb + 9·fat ≈ kcal). A clean food match reconciles tightly →
// High; a loose match diverges → Medium. (The agent also reports a per-portion
// confidence per ; this is the summary the chip shows for a /history row,
// which carries totals but not that per-step detail.)
export function confidenceOf(macros: MacroSummary): Confidence {
  if (macros.kcal <= 0) return { level: "High", pct: 90 };
  const atwater = 4 * macros.protein + 4 * macros.carb + 9 * macros.fat;
  const error = Math.abs(atwater - macros.kcal) / macros.kcal;
  const pct = Math.max(60, Math.min(97, Math.round(100 - error * 100)));
  return { level: error <= 0.12 ? "High" : "Medium", pct };
}
