import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MealTrace } from "@/components/meal-trace";
import { correctMeal, type ConfidenceAxis, type LoggedItem, type TraceStep } from "@/lib/api";

vi.mock("@/lib/api", () => ({ correctMeal: vi.fn() }));

// Two logged foods — including a double-counted "Burrito Bowl" the user will remove.
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

const ok = {
  ok: true,
  added_to_arize: true,
  corrections: 1,
  per_item: [],
  totals: [],
  phoenix_url: "https://app.phoenix.arize.com/s/demo",
};

describe("MealTrace", () => {
  it("keeps the agent's work behind a toggle, revealing each step on open", () => {
    render(<MealTrace trace={trace} perItem={perItem} />);
    // The breakdown table is always shown; the trace steps are tucked away.
    expect(screen.queryByText(/Parsed 2 foods/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /the agent's work/i }));
    expect(screen.getByText(/Parsed 2 foods/)).toBeInTheDocument();
    expect(screen.getByText(/Logged 2 items/)).toBeInTheDocument();
  });

  it("shows each item's scaled kcal", () => {
    render(<MealTrace trace={trace} perItem={perItem} mealText="chicken and a bowl" />);
    const row = screen.getByText("chicken breast, grilled").closest(".item-grid") as HTMLElement;
    expect(within(row).getByText("231")).toBeInTheDocument();
  });

  it("only offers a correction when there's a meal to correct", () => {
    const { rerender } = render(<MealTrace trace={trace} perItem={perItem} />);
    expect(
      screen.queryByRole("button", { name: /something's off/i }),
    ).not.toBeInTheDocument();
    rerender(<MealTrace trace={trace} perItem={perItem} mealText="x" />);
    expect(screen.getByRole("button", { name: /something's off/i })).toBeInTheDocument();
  });

  it("edits a portion and rescales the row", () => {
    render(<MealTrace trace={trace} perItem={perItem} mealText="x" />);
    fireEvent.click(screen.getByRole("button", { name: /something's off/i }));
    fireEvent.change(screen.getByLabelText(/grams of chicken breast, grilled/i), {
      target: { value: "280" },
    });
    const row = screen.getByText("chicken breast, grilled").closest(".item-grid") as HTMLElement;
    // 231 kcal at 140 g → 462 kcal at 280 g.
    expect(within(row).getByText("462")).toBeInTheDocument();
  });

  it("removes a double-counted item and saves only what's kept", async () => {
    vi.mocked(correctMeal).mockResolvedValue(ok);
    const onCorrected = vi.fn();
    render(
      <MealTrace
        trace={trace}
        perItem={perItem}
        mealText="chipotle bowl with chicken"
        onCorrected={onCorrected}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /something's off/i }));
    fireEvent.click(screen.getByRole("button", { name: /remove Chipotle Burrito Bowl/i }));
    fireEvent.click(screen.getByRole("button", { name: /save correction/i }));

    await waitFor(() => expect(correctMeal).toHaveBeenCalled());
    const [mealText, items] = vi.mocked(correctMeal).mock.calls[0];
    expect(mealText).toBe("chipotle bowl with chicken");
    expect(items.map((i) => i.description)).toEqual(["chicken breast, grilled"]);

    await waitFor(() => expect(screen.getByText(/Learned/i)).toBeInTheDocument());
    expect(onCorrected).toHaveBeenCalled();
  });

  it("passes mealId to correctMeal when provided", async () => {
    vi.clearAllMocks();
    vi.mocked(correctMeal).mockResolvedValue(ok);
    render(
      <MealTrace
        trace={trace}
        perItem={perItem}
        mealText="chicken and rice"
        mealId={42}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /something's off/i }));
    fireEvent.click(screen.getByRole("button", { name: /save correction/i }));

    await waitFor(() => expect(correctMeal).toHaveBeenCalled());
    const [, , mealId] = vi.mocked(correctMeal).mock.calls[0];
    expect(mealId).toBe(42);
  });

  // ──  all four confidence axes ──────────────────────────────────

  it("renders all four confidence axes when provided", () => {
    const axes: ConfidenceAxis[] = [
      { name: "resolution_completeness", score: 1.0, note: "✓ all 2 food(s) resolved" },
      { name: "source_quality", score: 1.0, note: "✓ high-trust sources" },
      { name: "portion_sanity", score: 1.0, note: "✓ all 2 portion(s) plausible" },
      { name: "calorie_plausibility", score: 1.0, note: "✓ 896 kcal ≈ Atwater estimate" },
    ];
    render(<MealTrace trace={trace} perItem={perItem} axes={axes} />);
    fireEvent.click(screen.getByRole("button", { name: /the agent's work/i }));
    expect(screen.getByText(/resolution completeness/i)).toBeInTheDocument();
    expect(screen.getByText(/source quality/i)).toBeInTheDocument();
    expect(screen.getByText(/portion sanity/i)).toBeInTheDocument();
    expect(screen.getByText(/calorie plausibility/i)).toBeInTheDocument();
    expect(screen.getByText("✓ all 2 food(s) resolved")).toBeInTheDocument();
  });

  it("shows ⚠ for a failing axis and ✓ for a passing one", () => {
    const axes: ConfidenceAxis[] = [
      { name: "resolution_completeness", score: 0.5, note: "⚠ 1 of 2 food(s) dropped (1 logged)" },
      { name: "source_quality", score: 1.0, note: "✓ high-trust sources" },
      { name: "portion_sanity", score: 1.0, note: "✓ all 1 portion(s) plausible" },
      { name: "calorie_plausibility", score: 1.0, note: "✓ 290 kcal ≈ Atwater estimate" },
    ];
    render(<MealTrace trace={trace} perItem={perItem} axes={axes} />);
    fireEvent.click(screen.getByRole("button", { name: /the agent's work/i }));
    expect(screen.getByText("⚠ 1 of 2 food(s) dropped (1 logged)")).toBeInTheDocument();
    expect(screen.getByText("✓ high-trust sources")).toBeInTheDocument();
  });

  // ──  per-portion basis note ────────────────────────────────────

  it("shows the portion basis note per item when provided", () => {
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
    // The basis should be visible without expanding the trace
    expect(screen.getByText(/reference serving/i)).toBeInTheDocument();
  });

  it("renders nothing extra when portion_basis is absent", () => {
    // Existing items without portion_basis should render cleanly — no errors.
    render(<MealTrace trace={trace} perItem={perItem} />);
    expect(screen.queryByText(/reference serving/i)).not.toBeInTheDocument();
  });
});
