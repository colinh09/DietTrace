import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MealTrace } from "@/components/meal-trace";
import type { ConfidenceAxis, LoggedItem, TraceStep } from "@/lib/api";

// FreeformFeedback (rendered when mealText is present) imports this.
vi.mock("@/lib/api", () => ({ submitFreeformFeedback: vi.fn() }));

const perItem: LoggedItem[] = [
  {
    fdc_id: 171477,
    description: "chicken breast, grilled",
    grams: 140,
    nutrients: [
      { code: "208", name: "Energy", amount: 231, unit: "kcal" },
      { code: "203", name: "Protein", amount: 43, unit: "g" },
      { code: "205", name: "Carbohydrate", amount: 0, unit: "g" },
      { code: "204", name: "Total lipid (fat)", amount: 5, unit: "g" },
    ],
  },
  {
    fdc_id: 999,
    description: "Chipotle Burrito Bowl",
    grams: 500,
    nutrients: [{ code: "208", name: "Energy", amount: 665, unit: "kcal" }],
  },
];

const trace: TraceStep[] = [
  { step: "parse_meal", summary: "Parsed 2 foods", foods: ["chicken", "bowl"] },
  { step: "log_entry", summary: "Logged 2 items", totals: perItem[0].nutrients },
];

describe("MealTrace", () => {
  it("shows the agent's work as cards (no toggle) — every step visible", () => {
    render(<MealTrace trace={trace} perItem={perItem} />);
    expect(screen.getByText(/agent's work/i)).toBeInTheDocument();
    expect(screen.getByText(/Parsed 2 foods/)).toBeInTheDocument();
    expect(screen.getByText(/Logged 2 items/)).toBeInTheDocument();
  });

  it("shows each item's kcal in the read-only table", () => {
    render(<MealTrace trace={trace} perItem={perItem} mealText="chicken and a bowl" />);
    const row = screen.getByText("chicken breast, grilled").closest(".item-grid") as HTMLElement;
    expect(within(row).getByText("231")).toBeInTheDocument();
  });

  it("offers the review (confirm / correct) only when there's a meal", () => {
    const { rerender } = render(<MealTrace trace={trace} perItem={perItem} />);
    expect(screen.queryByText(/does this look about right/i)).not.toBeInTheDocument();
    rerender(<MealTrace trace={trace} perItem={perItem} mealText="x" />);
    expect(screen.getByText(/does this look about right/i)).toBeInTheDocument();
    // The correction box is behind "No, something's off" (the correct path).
    expect(screen.queryByLabelText(/free-form feedback/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /no, something's off/i }));
    expect(screen.getByLabelText(/free-form feedback/i)).toBeInTheDocument();
  });

  // ── Confidence axes: the full calculation ────────────────────────────────

  it("renders all four confidence axes + the average total", () => {
    const axes: ConfidenceAxis[] = [
      { name: "resolution_completeness", score: 1.0, note: "✓ all 2 food(s) resolved" },
      { name: "source_quality", score: 1.0, note: "✓ high-trust sources" },
      { name: "portion_sanity", score: 1.0, note: "✓ all 2 portion(s) plausible" },
      { name: "calorie_plausibility", score: 1.0, note: "✓ 896 kcal ≈ Atwater estimate" },
    ];
    render(<MealTrace trace={trace} perItem={perItem} axes={axes} confidence={1.0} />);
    expect(screen.getByText(/foods found/i)).toBeInTheDocument();
    expect(screen.getByText(/trusted data/i)).toBeInTheDocument();
    expect(screen.getByText(/sensible portions/i)).toBeInTheDocument();
    expect(screen.getByText(/calories add up/i)).toBeInTheDocument();
    // The note renders without the ✓/⚠ glyph (it's encoded as the row class).
    expect(screen.getByText(/all 2 food\(s\) resolved/i)).toBeInTheDocument();
    // The actual calculation is spelled out.
    expect(screen.getByText(/average of 4 checks/i)).toBeInTheDocument();
    expect(screen.getByText(/100% confidence/i)).toBeInTheDocument();
  });

  it("marks a failing axis warn and a passing axis pass", () => {
    const axes: ConfidenceAxis[] = [
      { name: "resolution_completeness", score: 0.5, note: "⚠ 1 of 2 food(s) dropped (1 logged)" },
      { name: "source_quality", score: 1.0, note: "✓ high-trust sources" },
    ];
    render(<MealTrace trace={trace} perItem={perItem} axes={axes} confidence={0.75} />);
    const warnRow = screen.getByText(/1 of 2 food\(s\) dropped/i).closest(".conf-calc-row");
    expect(warnRow).toHaveClass("warn");
    expect(screen.getByText(/75% confidence/i)).toBeInTheDocument();
  });

  // ── Portion reasoning recap ───

  it("shows the 'why these foods & portions' card when basis is present", () => {
    const itemsWithBasis: LoggedItem[] = [
      {
        fdc_id: 1,
        description: "peanut butter",
        grams: 100,
        portion_basis: "no amount given → reference serving (Quantity not specified)",
        nutrients: [{ code: "208", name: "Energy", amount: 590, unit: "kcal" }],
      },
    ];
    render(<MealTrace trace={[]} perItem={itemsWithBasis} />);
    expect(screen.getByText(/why these foods/i)).toBeInTheDocument();
    expect(screen.getByText(/reference serving/i)).toBeInTheDocument();
  });

  it("renders no 'why these foods' card when portion_basis is absent", () => {
    render(<MealTrace trace={trace} perItem={perItem} />);
    expect(screen.queryByText(/why these foods/i)).not.toBeInTheDocument();
  });
});
