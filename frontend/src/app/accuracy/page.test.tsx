import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AccuracyPage from "@/app/accuracy/page";
import { getAccuracy, type AccuracyReport } from "@/lib/api";

vi.mock("@/lib/api", () => ({ getAccuracy: vi.fn() }));

const report: AccuracyReport = {
  headline: { calorie_accuracy: 0.6, macro_accuracy: 0.58, within_tolerance: 0.38 },
  metrics: [{ key: "macro", label: "Macro accuracy", baseline: 0.05, current: 0.58 }],
  loop: [
    { step: "trace", label: "traced to Phoenix" },
    { step: "evaluate", label: "scored vs USDA" },
    { step: "detect", label: "classified" },
    { step: "improve", label: "PR opened" },
  ],
  dataset: { cases: 16, source: "USDA FoodData Central (CC0)" },
  phoenix_url: "https://app.phoenix.arize.com/s/demo",
  source: "live",
  experiments: 3,
  trend: [
    { calorie: 0.02, macro: 0.05, within_tolerance: 0.0, portion: 0.13 },
    { calorie: 0.6, macro: 0.58, within_tolerance: 0.38, portion: 0.58 },
    { calorie: 0.9, macro: 0.88, within_tolerance: 0.75, portion: 0.89 },
  ],
};

describe("AccuracyPage", () => {
  it("renders the headline accuracy, the loop, and the live Arize source", async () => {
    vi.mocked(getAccuracy).mockResolvedValue(report);

    render(<AccuracyPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/How DietTrace stays accurate/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("60%")).toBeInTheDocument(); // calorie accuracy headline
    expect(screen.getByText(/how DietTrace checks its own work/i)).toBeInTheDocument();
    // The data is shown in-UI and labeled as live from Arize (no external link).
    expect(
      screen.getByText("Live from Arize Phoenix · 3 experiments"),
    ).toBeInTheDocument();
    // The accuracy-over-time trend renders.
    expect(screen.getByText(/accuracy over time · 3 experiments/i)).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /accuracy across experiments/i }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /View on Arize Phoenix/i }),
    ).not.toBeInTheDocument();
  });
});
