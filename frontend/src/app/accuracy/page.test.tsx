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
};

describe("AccuracyPage", () => {
  it("renders the headline accuracy, the loop, and the Phoenix link", async () => {
    vi.mocked(getAccuracy).mockResolvedValue(report);

    render(<AccuracyPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/How DietTrace stays accurate/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("60%")).toBeInTheDocument(); // calorie accuracy headline
    expect(screen.getByText(/the self-supervision loop/i)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /View on Arize Phoenix/i });
    expect(link).toHaveAttribute("href", report.phoenix_url);
  });
});
