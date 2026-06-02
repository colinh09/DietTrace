import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Dashboard } from "@/components/dashboard";
import type { RecentCorrection, TraceStep } from "@/lib/api";

const correction = (food: string, day: string): RecentCorrection => ({
  food,
  original_grams: 100,
  corrected_grams: 150,
  created_at: `2026-06-0${day}T12:00:00Z`,
});

describe("Dashboard", () => {
  it("shows the banked correction count and an empty-state prompt at zero", () => {
    render(<Dashboard corrections={0} taught={[]} latestTrace={null} />);

    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText(/your ground truth/i)).toBeInTheDocument();
    expect(screen.getByText(/banks it as ground truth/i)).toBeInTheDocument();
    // No chart and no re-tune control until there's something to show.
    expect(
      screen.queryByRole("img", { name: /corrections banked over time/i }),
    ).not.toBeInTheDocument();
  });

  it("renders the corrections-over-time chart once there are at least two", () => {
    const taught = [correction("banana", "1"), correction("chicken", "2")];
    render(<Dashboard corrections={2} taught={taught} latestTrace={null} />);

    expect(screen.getByText("2")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /2 corrections banked over time/i }),
    ).toBeInTheDocument();
    // The taught panel lists the fixes.
    expect(screen.getByText("banana")).toBeInTheDocument();
  });

  it("surfaces the latest meal's agent trace", () => {
    const steps: TraceStep[] = [
      { step: "parse_meal", summary: "parsed" },
      { step: "search_nutrition", summary: "found" },
      { step: "estimate_portion", summary: "120 g" },
    ];
    render(
      <Dashboard
        corrections={1}
        taught={[correction("banana", "1")]}
        latestTrace={{ text: "a banana", steps }}
      />,
    );

    expect(screen.getByText(/latest trace/i)).toBeInTheDocument();
    expect(screen.getByText("a banana")).toBeInTheDocument();
    expect(screen.getByText("parse_meal")).toBeInTheDocument();
    expect(screen.getByText("estimate_portion")).toBeInTheDocument();
  });
});
