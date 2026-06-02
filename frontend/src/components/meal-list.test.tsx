import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MealList, type MealDetail } from "@/components/meal-list";
import type { LoggedItem, Meal, TraceStep } from "@/lib/api";

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

  it("offers a remove affordance and an expand chevron per row", () => {
    render(<MealList meals={meals} />);
    const row = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    expect(within(row).getByRole("button", { name: /remove/i })).toBeInTheDocument();
    // The row head is itself the expand toggle, collapsed by default.
    const head = within(row).getByRole("button", { name: /expand/i });
    expect(head).toHaveAttribute("aria-expanded", "false");
  });

  it("toggles the row open when the chevron head is clicked", () => {
    render(<MealList meals={meals} />);
    const row = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    const head = within(row).getByRole("button", { name: /expand/i });
    fireEvent.click(head);
    expect(head).toHaveAttribute("aria-expanded", "true");
  });

  it("shows a calm empty state when nothing is logged", () => {
    render(<MealList meals={[]} />);
    expect(screen.getByText(/nothing logged/i)).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("reveals the agent's-work trace from the /log detail when a row is expanded", () => {
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
    // Collapsed by default: the trace is not in the DOM.
    expect(screen.queryByText(/the agent's work/i)).not.toBeInTheDocument();

    const row = screen.getByText("grilled chicken salad with olive oil").closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: /expand/i }));
    expect(within(row).getByText(/the agent's work/i)).toBeInTheDocument();
    expect(within(row).getByText(/Parsed 1 food/)).toBeInTheDocument();
    // The portion shows read-only; correcting it is one click away.
    expect(within(row).getByText("140 g")).toBeInTheDocument();
    expect(
      within(row).getByRole("button", { name: /something's off/i }),
    ).toBeInTheDocument();
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

  it("shows the confidence reasons when a row with a backend score is expanded", () => {
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
    // Collapsed: the reasons aren't in the DOM yet.
    expect(screen.queryByText(/lower-trust source/)).not.toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: /expand/i }));
    expect(within(row).getByText(/lower-trust source/)).toBeInTheDocument();
    expect(within(row).getByText(/macros total zero energy/)).toBeInTheDocument();
  });

  it("shows a calm note when an expanded row has no trace detail", () => {
    render(<MealList meals={meals} />);
    const row = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: /expand/i }));
    expect(within(row).getByText(/no agent trace/i)).toBeInTheDocument();
  });
});
