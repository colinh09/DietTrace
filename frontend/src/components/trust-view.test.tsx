import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TrustView } from "@/components/trust-view";
import type { FeedbackItem, TrustReport } from "@/lib/api";

const report: TrustReport = {
  count: 3,
  mean_confidence: 0.9,
  needs_review_pct: 0.1,
  source_breakdown: { usda: 3 },
  recent_low_confidence: [],
};

const corrections: FeedbackItem[] = [
  { id: 1, created_at: "x", feedback_text: "before workouts I eat more carbs", meal_text: null, weight: 2 },
  { id: 2, created_at: "x", feedback_text: "my oats are a bigger portion", meal_text: null, weight: 1 },
];

describe("TrustView", () => {
  it("surfaces the corrections taught when provided (the observability view)", () => {
    render(<TrustView report={report} corrections={corrections} />);
    expect(screen.getByText(/corrections you've taught/i)).toBeInTheDocument();
    expect(screen.getByText(/before workouts I eat more carbs/)).toBeInTheDocument();
    // The emphasized correction is marked.
    expect(screen.getByText(/emphasized/i)).toBeInTheDocument();
  });

  it("omits the corrections section on the standalone route (no corrections)", () => {
    render(<TrustView report={report} />);
    expect(screen.queryByText(/corrections you've taught/i)).not.toBeInTheDocument();
  });
});
