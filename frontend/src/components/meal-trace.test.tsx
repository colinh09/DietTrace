import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MealTrace } from "@/components/meal-trace";
import type { LoggedItem, TraceStep } from "@/lib/api";

// One logged food at 140 g, with its nutrient panel scaled to that portion.
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
];

// The agent's reconstructed steps, exactly as `/log` returns them.
const trace: TraceStep[] = [
  {
    step: "parse_meal",
    summary: "Parsed 1 food(s): chicken breast, grilled",
    foods: ["chicken breast, grilled"],
  },
  {
    step: "search_nutrition",
    summary: "Matched 'chicken breast, grilled' to USDA food 171477",
    food: "chicken breast, grilled",
    matched: "chicken breast, grilled",
    fdc_id: 171477,
  },
  {
    step: "estimate_portion",
    summary: "Estimated 140 g for 'chicken breast, grilled'",
    food: "chicken breast, grilled",
    grams: 140,
  },
  {
    step: "log_entry",
    summary: "Logged 1 item(s) into 4 nutrient total(s)",
    totals: perItem[0].nutrients,
  },
];

describe("MealTrace", () => {
  it("labels the section as the agent's work", () => {
    render(<MealTrace trace={trace} perItem={perItem} />);
    expect(screen.getByText(/the agent's work/i)).toBeInTheDocument();
  });

  it("renders one calm line per trace step, in order", () => {
    render(<MealTrace trace={trace} perItem={perItem} />);
    const steps = screen.getAllByRole("listitem");
    expect(steps).toHaveLength(trace.length);
    expect(screen.getByText(/Parsed 1 food/)).toBeInTheDocument();
    expect(screen.getByText(/Matched 'chicken breast, grilled' to USDA food 171477/)).toBeInTheDocument();
    expect(screen.getByText(/Estimated 140 g/)).toBeInTheDocument();
    expect(screen.getByText(/Logged 1 item/)).toBeInTheDocument();
  });

  it("renders an editable grams field per item, seeded from the logged portion", () => {
    render(<MealTrace trace={trace} perItem={perItem} />);
    const grams = screen.getByLabelText(/grams of chicken breast, grilled/i) as HTMLInputElement;
    expect(grams).toHaveValue(140);
  });

  it("shows the item's scaled kcal and macros", () => {
    render(<MealTrace trace={trace} perItem={perItem} />);
    const row = screen.getByText("chicken breast, grilled").closest(".item-grid") as HTMLElement;
    expect(within(row).getByText("231")).toBeInTheDocument();
  });

  it("rescales kcal and macros when grams are edited", () => {
    render(<MealTrace trace={trace} perItem={perItem} />);
    const grams = screen.getByLabelText(/grams of chicken breast, grilled/i);
    fireEvent.change(grams, { target: { value: "280" } });
    const row = screen.getByText("chicken breast, grilled").closest(".item-grid") as HTMLElement;
    // 231 kcal at 140 g → 462 kcal at 280 g.
    expect(within(row).getByText("462")).toBeInTheDocument();
  });
});
