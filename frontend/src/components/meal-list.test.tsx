import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MealList } from "@/components/meal-list";
import type { Meal } from "@/lib/api";

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

  it("offers an edit affordance and an expand chevron per row", () => {
    render(<MealList meals={meals} />);
    const row = screen.getByText("a mystery pastry").closest("li") as HTMLElement;
    expect(within(row).getByRole("button", { name: /edit/i })).toBeInTheDocument();
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
});
