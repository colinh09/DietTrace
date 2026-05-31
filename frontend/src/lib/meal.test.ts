import { describe, expect, it } from "vitest";
import type { Nutrient } from "@/lib/api";
import { confidenceOf, macrosOf } from "@/lib/meal";

// A nutrient panel keyed by the USDA number codes the row reads.
function totals(kcal: number, p: number, c: number, f: number): Nutrient[] {
  return [
    { code: "208", name: "Energy", amount: kcal, unit: "kcal" },
    { code: "203", name: "Protein", amount: p, unit: "g" },
    { code: "205", name: "Carbohydrate", amount: c, unit: "g" },
    { code: "204", name: "Total lipid (fat)", amount: f, unit: "g" },
  ];
}

describe("macrosOf", () => {
  it("pulls kcal/protein/carb/fat out of a nutrient panel by USDA code", () => {
    expect(macrosOf(totals(400, 30, 40, 11.6))).toEqual({
      kcal: 400,
      protein: 30,
      carb: 40,
      fat: 11.6,
    });
  });

  it("falls back to zero for any macro the panel omits", () => {
    expect(macrosOf([{ code: "208", name: "Energy", amount: 90, unit: "kcal" }])).toEqual({
      kcal: 90,
      protein: 0,
      carb: 0,
      fat: 0,
    });
  });
});

describe("confidenceOf", () => {
  it("rates a meal High when its macros reconcile to its calorie total", () => {
    // 4·30 + 4·40 + 9·11.6 = 384.4 ≈ 400 kcal → tight Atwater match.
    const conf = confidenceOf(macrosOf(totals(400, 30, 40, 11.6)));
    expect(conf.level).toBe("High");
    expect(conf.pct).toBeGreaterThanOrEqual(88);
  });

  it("rates a meal Medium when its macros diverge from its calorie total", () => {
    // 4·10 + 4·10 + 9·5 = 125, far below 500 kcal → loose match.
    const conf = confidenceOf(macrosOf(totals(500, 10, 10, 5)));
    expect(conf.level).toBe("Medium");
    expect(conf.pct).toBeLessThan(88);
  });

  it("defaults to High when there are no calories to reconcile against", () => {
    expect(confidenceOf(macrosOf(totals(0, 0, 0, 0)))).toEqual({ level: "High", pct: 90 });
  });
});
