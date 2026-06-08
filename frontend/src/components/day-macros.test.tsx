import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DayMacros } from "@/components/day-macros";
import type { GoalProgress } from "@/lib/api";

// A day partway to each target: calories half done, protein over target.
const goals: GoalProgress[] = [
  { code: "208", name: "Energy", unit: "kcal", target: 2000, consumed: 1000, remaining: 1000 },
  { code: "203", name: "Protein", unit: "g", target: 150, consumed: 180, remaining: -30 },
  { code: "205", name: "Carbohydrate", unit: "g", target: 200, consumed: 50, remaining: 150 },
  { code: "204", name: "Total lipid (fat)", unit: "g", target: 65, consumed: 13, remaining: 52 },
];

describe("DayMacros", () => {
  it("shows calories consumed against the target", () => {
    render(<DayMacros goals={goals} />);
    expect(screen.getByText("calories")).toBeInTheDocument();
    // Big number is consumed; the goal is shown as "/ 2,000".
    expect(screen.getByText("1,000")).toBeInTheDocument();
    expect(screen.getByText("/ 2,000")).toBeInTheDocument();
  });

  it("shows P/C/F consumed against their gram targets", () => {
    render(<DayMacros goals={goals} />);
    expect(screen.getByText("P")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    expect(screen.getByText("F")).toBeInTheDocument();
    expect(screen.getByText("180 / 150 g")).toBeInTheDocument();
    expect(screen.getByText("50 / 200 g")).toBeInTheDocument();
    expect(screen.getByText("13 / 65 g")).toBeInTheDocument();
  });

  it("renders a calorie ring and a labeled bar per macro", () => {
    render(<DayMacros goals={goals} />);
    // calories ring + P/C/F bars = four accessible graphics (role="img").
    const graphics = screen.getAllByRole("img");
    expect(graphics).toHaveLength(4);

    // Each label encodes consumed-of-target; an over-target macro still reports
    // its true numbers (the fill clamps, the label doesn't lie).
    expect(
      screen.getByRole("img", { name: /calories: 1000 of 2000/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /protein: 180 of 150/i }),
    ).toBeInTheDocument();
  });

  it("falls back to zeros when a macro is missing", () => {
    render(<DayMacros goals={[]} />);
    // The calorie ring center reads 0; each macro bar reads "0 / 0 g".
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getAllByText("0 / 0 g")).toHaveLength(3);
  });

  it("rounds fractional amounts for display", () => {
    render(
      <DayMacros
        goals={[
          { code: "208", name: "Energy", unit: "kcal", target: 2000, consumed: 1234.6, remaining: 765.4 },
        ]}
      />,
    );
    const band = screen.getByText("calories").closest("section") as HTMLElement;
    expect(within(band).getByText("1,235")).toBeInTheDocument();
  });
});
