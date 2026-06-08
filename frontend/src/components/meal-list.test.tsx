import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MealList, type MealDetail } from "@/components/meal-list";
import type { LoggedItem, Meal, TraceStep } from "@/lib/api";

// Meals collapse to a one-line summary by default; click the row to expand.
const expandMeal = (row: HTMLElement) =>
  fireEvent.click(row.querySelector(".meal-head") as HTMLElement);

// Two days-worth of /history meals: one whose macros reconcile cleanly (High)
// and one whose macros diverge from its calorie total (Medium).
const meals: Meal[] = [
  {
    id: 2,
    created_at: new Date(2026, 4, 30, 12, 30).toISOString(),
    date: "2026-05-30",
    text: "grilled chicken salad with olive oil",
    totals: [
      { code: "208", name: "Energy", amount: 432, unit: "kcal" },
      { code: "203", name: "Protein", amount: 41, unit: "g" },
      { code: "205", name: "Carbohydrate", amount: 9, unit: "g" },
      { code: "204", name: "Total lipid (fat)", amount: 26, unit: "g" },
    ],
  },
  {
    id: 1,
    created_at: new Date(2026, 4, 30, 8, 14).toISOString(),
    date: "2026-05-30",
    text: "a mystery pastry",
    totals: [
      { code: "208", name: "Energy", amount: 500, unit: "kcal" },
      { code: "203", name: "Protein", amount: 4, unit: "g" },
      { code: "205", name: "Carbohydrate", amount: 20, unit: "g" },
      { code: "204", name: "Total lipid (fat)", amount: 5, unit: "g" },
    ],
  },
];

describe("MealList", () => {
  it("renders one compact row per meal with its text", () => {
    render(<MealList meals={meals} />);
    expect(screen.getByText("grilled chicken salad with olive oil")).toBeInTheDocument();
    expect(screen.getByText("a mystery pastry")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("shows the meal count in the heading", () => {
    render(<MealList meals={meals} />);
    expect(screen.getByText(/2 meals/i)).toBeInTheDocument();
  });

  it("shows kcal and P/C/F inline for a row", () => {
    render(<MealList meals={meals} />);
    const row = screen.getByText("grilled chicken salad with olive oil").closest("li") as HTMLElement;
    expect(within(row).getByText("432")).toBeInTheDocument();
    expect(within(row).getByText(/P\s*41/)).toBeInTheDocument();
    expect(within(row).getByText(/C\s*9/)).toBeInTheDocument();
    expect(within(row).getByText(/F\s*26/)).toBeInTheDocument();
  });

  it("renders the meal's logged time", () => {
    render(<MealList meals={meals} />);
    const row = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    expect(within(row).getByText(/^\d{1,2}:\d{2}\s?(AM|PM)$/)).toBeInTheDocument();
  });

  it("renders a confidence chip per row — High when macros reconcile, Medium when they diverge", () => {
    render(<MealList meals={meals} />);
    const clean = screen.getByText("grilled chicken salad with olive oil").closest("li") as HTMLElement;
    expect(within(clean).getByText(/High/)).toBeInTheDocument();

    const loose = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    expect(within(loose).getByText(/Medium/)).toBeInTheDocument();
  });

  it("offers a remove affordance per row and no separate expander", () => {
    render(<MealList meals={meals} />);
    const row = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    expect(within(row).getByRole("button", { name: /remove/i })).toBeInTheDocument();
    // The breakdown is always shown now, so there is no chevron/expand control.
    expect(
      within(row).queryByRole("button", { name: /expand/i }),
    ).not.toBeInTheDocument();
  });

  it("shows a calm empty state when nothing is logged", () => {
    render(<MealList meals={[]} />);
    expect(screen.getByText(/nothing logged/i)).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("reveals the breakdown when expanded, with the trace behind the agent's-work dropdown", () => {
    const perItem: LoggedItem[] = [
      {
        fdc_id: 171477,
        description: "grilled chicken",
        grams: 140,
        nutrients: [{ code: "208", name: "Energy", amount: 231, unit: "kcal" }],
      },
    ];
    const trace: TraceStep[] = [
      { step: "parse_meal", summary: "Parsed 1 food(s): grilled chicken", foods: ["grilled chicken"] },
      { step: "log_entry", summary: "Logged 1 item(s) into 1 nutrient total(s)", totals: perItem[0].nutrients },
    ];
    render(<MealList meals={meals} detailsById={{ 2: { trace, perItem } }} />);

    const row = screen.getByText("grilled chicken salad with olive oil").closest("li") as HTMLElement;
    // Collapsed by default — the breakdown is hidden until the row is expanded.
    expect(within(row).queryByText("140 g")).not.toBeInTheDocument();
    expandMeal(row);
    expect(within(row).getByText("140 g")).toBeInTheDocument();
    // The review step (confirm / tweak / correct) is the single correction surface.
    expect(within(row).getByText(/does this look about right/i)).toBeInTheDocument();
    // The trace steps are an always-visible "agent's work" card once expanded.
    expect(within(row).getByText(/Parsed 1 food/)).toBeInTheDocument();
  });

  it("uses the backend confidence from the meal's detail over the macro heuristic", () => {
    // The clean meal's macros reconcile (heuristic → High), but the backend's
    // online-eval scored it low; the chip must follow the backend value (12.2).
    const detail: MealDetail = {
      trace: [],
      perItem: [],
      confidence: 0.42,
      reasons: ["lower-trust source(s): web"],
    };
    render(<MealList meals={meals} detailsById={{ 2: detail }} />);
    const clean = screen
      .getByText("grilled chicken salad with olive oil")
      .closest("li") as HTMLElement;
    expect(within(clean).getByText(/Medium/)).toBeInTheDocument();
    expect(within(clean).getByText(/42%/)).toBeInTheDocument();
  });

  it("gives the confidence chip a styled tooltip (focusable) when axes are present", () => {
    const detail: MealDetail = {
      trace: [],
      perItem: [],
      confidence: 0.66,
      axes: [
        { name: "resolution_completeness", score: 1, note: "✓ all foods resolved" },
        { name: "source_quality", score: 1, note: "✓ USDA sources" },
        { name: "portion_sanity", score: 0.5, note: "⚠ a portion looks off" },
        { name: "calorie_plausibility", score: 1, note: "✓ calories add up" },
      ],
    };
    render(<MealList meals={meals} detailsById={{ 2: detail }} />);
    const clean = screen
      .getByText("grilled chicken salad with olive oil")
      .closest("li") as HTMLElement;
    // The styled tooltip renders the four plain-language checks…
    const tip = within(clean).getByRole("tooltip");
    expect(within(tip).getByText("Sensible portions")).toBeInTheDocument();
    // …and the chip is keyboard-focusable (the hover-only title is dropped).
    const chip = clean.querySelector(".conf-chip") as HTMLElement;
    expect(chip).toHaveAttribute("tabindex", "0");
    expect(chip).not.toHaveAttribute("title");
  });

  it("shows the confidence reasons in the 'why this confidence' card when expanded", () => {
    const detail: MealDetail = {
      trace: [
        { step: "parse_meal", summary: "Parsed 1 food(s): chicken", foods: ["chicken"] },
      ],
      perItem: [],
      confidence: 0.42,
      reasons: ["lower-trust source(s): web", "118 kcal logged but the macros total zero energy"],
    };
    render(<MealList meals={meals} detailsById={{ 2: detail }} />);
    const row = screen
      .getByText("grilled chicken salad with olive oil")
      .closest("li") as HTMLElement;
    // Hidden until the meal row is expanded; then visible as a card (no toggle).
    expect(screen.queryByText(/lower-trust source/)).not.toBeInTheDocument();
    expandMeal(row);
    expect(within(row).getByText(/lower-trust source/)).toBeInTheDocument();
    expect(within(row).getByText(/macros total zero energy/)).toBeInTheDocument();
  });

  it("offers a review flag only when the backend flags needs_review (12.3)", () => {
    const flagged: MealDetail = {
      trace: [],
      perItem: [],
      confidence: 0.42,
      reasons: ["lower-trust source(s): web"],
      needsReview: true,
      reviewReason: "lower-trust source(s): web",
    };
    render(<MealList meals={meals} detailsById={{ 2: flagged }} />);

    const flaggedRow = screen
      .getByText("grilled chicken salad with olive oil")
      .closest("li") as HTMLElement;
    expect(
      within(flaggedRow).getByRole("button", { name: /why this was flagged/i }),
    ).toBeInTheDocument();

    // A meal with no review flag (the other row) shows no review affordance.
    const calmRow = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    expect(
      within(calmRow).queryByRole("button", { name: /why this was flagged/i }),
    ).not.toBeInTheDocument();
  });

  it("review flag opens the agent's work so the user can see why it's flagged", () => {
    const flagged: MealDetail = {
      trace: [
        { step: "parse_meal", summary: "Parsed 1 food(s): chicken", foods: ["chicken"] },
      ],
      perItem: [],
      confidence: 0.42,
      reasons: ["lower-trust source(s): web"],
      needsReview: true,
      reviewReason: "lower-trust source(s): web",
    };
    render(<MealList meals={meals} detailsById={{ 2: flagged }} />);
    const row = screen
      .getByText("grilled chicken salad with olive oil")
      .closest("li") as HTMLElement;

    // Trace hidden until the review flag is clicked.
    expect(within(row).queryByText(/Parsed 1 food/)).not.toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: /why this was flagged/i }));
    expect(within(row).getByText(/Parsed 1 food/)).toBeInTheDocument();
  });

  it("shows a calm note when a row has no breakdown detail", () => {
    render(<MealList meals={meals} />);
    const row = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    // No /log detail captured for this history row → a calm note once expanded.
    expandMeal(row);
    expect(within(row).getByText(/no breakdown/i)).toBeInTheDocument();
  });

  it("renders trace steps for a history-loaded meal once the row is expanded", () => {
    // Simulate a meal as /history returns it — per_item + trace from the persisted
    // detail (or rebuilt by the history endpoint for older logs).
    const historyTrace: TraceStep[] = [
      { step: "parse_meal", summary: "Parsed 1 food(s): banana", foods: ["banana"] },
      { step: "web_search", summary: "Searched the web for 'banana' (not in USDA)", food: "banana", matched: "banana" },
      { step: "estimate_portion", summary: "Estimated 118 g for 'banana'", food: "banana", grams: 118 },
      { step: "log_entry", summary: "Logged 1 item(s) into 1 nutrient total(s)", totals: [] },
    ];
    const historyPerItem: LoggedItem[] = [
      { fdc_id: 0, description: "banana", grams: 118, nutrients: [{ code: "208", name: "Energy", amount: 89, unit: "kcal" }] },
    ];
    const historyMeal: Meal = {
      id: 55,
      created_at: new Date(2026, 5, 4, 9, 0).toISOString(),
      date: "2026-06-04",
      text: "a banana for breakfast",
      totals: [{ code: "208", name: "Energy", amount: 89, unit: "kcal" }],
      per_item: historyPerItem,
      trace: historyTrace,
      confidence: 0.88,
      reasons: [],
    };

    // Build detailsById exactly as loadHistory does in page.tsx: from per_item + trace
    // on the history-response Meal, only when no session-level detail exists yet.
    const detailsById: Record<number, MealDetail> = {};
    if (historyMeal.per_item && detailsById[historyMeal.id] == null) {
      detailsById[historyMeal.id] = {
        trace: historyMeal.trace ?? [],
        perItem: historyMeal.per_item,
        confidence: historyMeal.confidence,
        reasons: historyMeal.reasons,
        needsReview: historyMeal.needs_review,
        reviewReason: historyMeal.review_reason ?? null,
      };
    }

    render(<MealList meals={[historyMeal]} detailsById={detailsById} />);
    const row = screen.getByText("a banana for breakfast").closest("li") as HTMLElement;

    // Trace steps are hidden before expansion.
    expect(within(row).queryByText(/Parsed 1 food/)).not.toBeInTheDocument();

    // Expanding the row reveals the always-visible agent's-work card.
    expandMeal(row);

    expect(within(row).getByText(/Parsed 1 food/)).toBeInTheDocument();
    expect(within(row).getByText(/Searched the web for 'banana'/)).toBeInTheDocument();
    expect(within(row).getByText(/Estimated 118 g/)).toBeInTheDocument();
    expect(within(row).getByText(/Logged 1 item/)).toBeInTheDocument();
  });

  it("renders a dataset point with full detail: badge, macros, and a breakdown", () => {
    const datasetMeal: Meal = {
      id: 9,
      created_at: new Date(2026, 4, 29, 9, 0).toISOString(),
      date: "2026-05-29",
      text: "a big bowl of white rice before my run",
      totals: [
        { code: "208", name: "Energy", amount: 418, unit: "kcal" },
        { code: "203", name: "Protein", amount: 8, unit: "g" },
        { code: "205", name: "Carbohydrate", amount: 90, unit: "g" },
        { code: "204", name: "Total lipid (fat)", amount: 1, unit: "g" },
      ],
      per_item: [
        {
          fdc_id: 123,
          description: "Rice, white, cooked",
          grams: 370,
          nutrients: [{ code: "208", name: "Energy", amount: 418, unit: "kcal" }],
        },
      ],
      dataset_point: true,
    };
    render(<MealList meals={[datasetMeal]} />);
    const row = screen.getByText(/a big bowl of white rice/).closest("li") as HTMLElement;

    // Badged as a dataset point AND keeping its confidence chip (the badge is an
    // extra tag, not a replacement), with real macros.
    expect(within(row).getByText(/dataset point/i)).toBeInTheDocument();
    expect(row.querySelector(".conf-chip")).not.toBeNull();
    expect(within(row).getByText(/418/)).toBeInTheDocument();
    expect(within(row).getByText(/P 8/)).toBeInTheDocument();

    // Expanding shows its held-out role AND the full per-item breakdown.
    expandMeal(row);
    expect(within(row).getByText(/Held-out ground truth/i)).toBeInTheDocument();
    expect(within(row).getByText(/Rice, white, cooked/)).toBeInTheDocument();
  });

  it("badges a meal the user gave feedback on, alongside its confidence chip", () => {
    const meal: Meal = {
      id: 11,
      created_at: new Date(2026, 4, 29, 9, 0).toISOString(),
      date: "2026-05-29",
      text: "preworkout oats",
      totals: [{ code: "208", name: "Energy", amount: 300, unit: "kcal" }],
      has_feedback: true,
    };
    render(<MealList meals={[meal]} />);
    const row = screen.getByText(/preworkout oats/).closest("li") as HTMLElement;
    expect(within(row).getByText(/feedback/i)).toBeInTheDocument();
    expect(row.querySelector(".conf-chip")).not.toBeNull(); // chip kept alongside
  });
});
