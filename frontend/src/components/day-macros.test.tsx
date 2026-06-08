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

// The calorie ring zone — scoped so the big consumed number isn't confused with
// the glance zone's "kcal remaining" figure (which can share the same value).
const calZone = (c: HTMLElement) => c.querySelector(".dm-cal") as HTMLElement;
const glance = (c: HTMLElement) => c.querySelector(".dm-glance") as HTMLElement;

describe("DayMacros", () => {
  it("shows calories consumed against the target", () => {
    const { container } = render(<DayMacros goals={goals} />);
    expect(screen.getByText("calories")).toBeInTheDocument();
    // Big number is consumed; the goal is shown as "/ 2,000".
    expect(within(calZone(container)).getByText("1,000")).toBeInTheDocument();
    expect(screen.getByText("/ 2,000")).toBeInTheDocument();
  });

  it("shows P/C/F consumed against their gram targets", () => {
    render(<DayMacros goals={goals} />);
    expect(screen.getByText("P")).toBeInTheDocument();
    expect(screen.getByText("C")).toBeInTheDocument();
    expect(screen.getByText("F")).toBeInTheDocument();
    // The consumed number sits in a <b> (so it reads dark, not faint), so the
    // value text spans nodes — match on the bar-value's normalized text content.
    const barVal = (t: string) =>
      screen.getByText(
        (_c, el) =>
          el?.classList.contains("dm-bar-val") === true &&
          el.textContent?.replace(/\s+/g, " ").trim() === t,
      );
    expect(barVal("180 / 150 g")).toBeInTheDocument();
    expect(barVal("50 / 200 g")).toBeInTheDocument();
    expect(barVal("13 / 65 g")).toBeInTheDocument();
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
    const { container } = render(<DayMacros goals={[]} />);
    // The calorie ring center reads 0; each macro bar reads "0 / 0 g".
    expect(within(calZone(container)).getByText("0")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        (_c, el) =>
          el?.classList.contains("dm-bar-val") === true &&
          el.textContent?.replace(/\s+/g, " ").trim() === "0 / 0 g",
      ),
    ).toHaveLength(3);
  });

  it("rounds fractional amounts for display", () => {
    const { container } = render(
      <DayMacros
        goals={[
          { code: "208", name: "Energy", unit: "kcal", target: 2000, consumed: 1234.6, remaining: 765.4 },
        ]}
      />,
    );
    expect(within(calZone(container)).getByText("1,235")).toBeInTheDocument();
  });

  // ── Glance zone: kcal remaining + learning counts ──────────────────────────
  it("shows kcal remaining for the day in the glance zone", () => {
    const { container } = render(<DayMacros goals={goals} />);
    const zone = glance(container);
    expect(zone).not.toBeNull();
    // 2000 target − 1000 consumed = 1000 remaining.
    expect(within(zone).getByText("1,000")).toBeInTheDocument();
    expect(within(zone).getByText(/kcal remaining/i)).toBeInTheDocument();
  });

  it("reads 'over' when the calorie target is exceeded", () => {
    const { container } = render(
      <DayMacros
        goals={[
          { code: "208", name: "Energy", unit: "kcal", target: 2000, consumed: 2300, remaining: -300 },
        ]}
      />,
    );
    const zone = glance(container);
    expect(within(zone).getByText("300")).toBeInTheDocument();
    expect(within(zone).getByText(/kcal over/i)).toBeInTheDocument();
  });

  it("shows the learning-loop counts in the glance zone", () => {
    const { container } = render(
      <DayMacros
        goals={goals}
        stats={{ corrections: 3, confirmations: 6, version: 2 }}
      />,
    );
    const zone = glance(container);
    const stats = within(zone).getByLabelText(/learning progress/i);
    expect(within(stats).getByText("3")).toBeInTheDocument();
    expect(within(stats).getByText(/feedbacks banked/i)).toBeInTheDocument();
    expect(within(stats).getByText("2")).toBeInTheDocument();
    expect(within(stats).getByText(/re-tunes shipped/i)).toBeInTheDocument();
    expect(within(stats).getByText("6")).toBeInTheDocument();
    expect(within(stats).getByText(/in your dataset/i)).toBeInTheDocument();
  });

  it("falls back to zero counts before the stats have loaded", () => {
    const { container } = render(<DayMacros goals={goals} />);
    const stats = within(glance(container)).getByLabelText(/learning progress/i);
    expect(within(stats).getAllByText("0")).toHaveLength(3);
  });
});
