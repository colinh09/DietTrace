import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfidenceTooltip } from "@/components/confidence-tooltip";
import type { ConfidenceAxis } from "@/lib/api";

const axes: ConfidenceAxis[] = [
  { name: "resolution_completeness", score: 1.0, note: "✓ all foods resolved" },
  { name: "source_quality", score: 1.0, note: "✓ USDA sources" },
  { name: "portion_sanity", score: 0.5, note: "⚠ a portion looks off" },
  { name: "calorie_plausibility", score: 1.0, note: "✓ calories add up" },
];

describe("ConfidenceTooltip", () => {
  it("wraps its children and renders the four axis checks with plain labels", () => {
    render(
      <ConfidenceTooltip pct={88} level="High" axes={axes}>
        <span className="chip">High · 88%</span>
      </ConfidenceTooltip>,
    );
    // The chip (children) is rendered as the anchor.
    expect(screen.getByText("High · 88%")).toBeInTheDocument();

    const tip = screen.getByRole("tooltip");
    // Plain-English axis labels (not the raw jargon names).
    expect(within(tip).getByText("Sensible portions")).toBeInTheDocument();
    expect(within(tip).getByText("Foods found")).toBeInTheDocument();
    expect(within(tip).getByText("Trusted data")).toBeInTheDocument();
    expect(within(tip).getByText("Calories add up")).toBeInTheDocument();
    // A "Learn more" disclosure replaces the giant native title string.
    expect(within(tip).getByText(/learn more/i)).toBeInTheDocument();
  });

  it("flags the low axis with a lo marker on its value", () => {
    render(
      <ConfidenceTooltip pct={88} level="High" axes={axes}>
        <span className="chip">High · 88%</span>
      </ConfidenceTooltip>,
    );
    const tip = screen.getByRole("tooltip");
    const lowRow = within(tip).getByText("Sensible portions").closest(".tip-check");
    expect(lowRow?.querySelector(".v.lo")).not.toBeNull();
  });

  it("renders just the children (no tooltip) when there are no axes", () => {
    render(
      <ConfidenceTooltip pct={88} level="High">
        <span className="chip">High · 88%</span>
      </ConfidenceTooltip>,
    );
    expect(screen.getByText("High · 88%")).toBeInTheDocument();
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
