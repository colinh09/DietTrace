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
    expect(screen.getByText("/ 150 g")).toBeInTheDocument();
    expect(screen.getByText("/ 200 g")).toBeInTheDocument();
    expect(screen.getByText("/ 65 g")).toBeInTheDocument();
  });

  it("renders a sage progress bar per macro, clamped to 0–100%", () => {
    render(<DayMacros goals={goals} />);
    const bars = screen.getAllByRole("progressbar");
    // calories + P + C + F.
    expect(bars).toHaveLength(4);

    const cal = screen.getByRole("progressbar", { name: /calories/i });
    expect(cal).toHaveStyle({ width: "50%" });

    // Protein is over target → the fill clamps at 100%, not 120%.
    const protein = screen.getByRole("progressbar", { name: /protein/i });
    expect(protein).toHaveStyle({ width: "100%" });

    const carb = screen.getByRole("progressbar", { name: /carbohydrate/i });
    expect(carb).toHaveStyle({ width: "25%" });
  });

  it("falls back to zeros when a macro is missing", () => {
    render(<DayMacros goals={[]} />);
    // Calories + P + C + F all read zero.
    expect(screen.getAllByText("0")).toHaveLength(4);
    const bars = screen.getAllByRole("progressbar");
    for (const bar of bars) {
      expect(bar).toHaveStyle({ width: "0%" });
    }
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
