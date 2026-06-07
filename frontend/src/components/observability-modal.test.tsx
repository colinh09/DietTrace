import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OverviewModal } from "@/components/observability-modal";
import {
  getAccuracy,
  getTrust,
  listLearningFeedback,
  type AccuracyReport,
  type TrustReport,
} from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getAccuracy: vi.fn(),
  getTrust: vi.fn(),
  listLearningFeedback: vi.fn(),
}));

const accuracy: AccuracyReport = {
  headline: { calorie_accuracy: 0.81, macro_accuracy: 0.81, within_tolerance: 0.75 },
  metrics: [{ key: "macro", label: "Macro accuracy", baseline: 0.05, current: 0.81 }],
  loop: [{ step: "trace", label: "traced" }],
  dataset: { cases: 8, source: "USDA FDC" },
  phoenix_url: "",
  source: "live",
  experiments: 4,
  trend: [],
};

const trust: TrustReport = {
  count: 3,
  mean_confidence: 0.9,
  needs_review_pct: 0.1,
  source_breakdown: { usda: 3 },
  recent_low_confidence: [],
};

describe("OverviewModal", () => {
  it("shows the project intro with Accuracy and Trust stacked on one page", async () => {
    vi.mocked(getAccuracy).mockResolvedValue(accuracy);
    vi.mocked(getTrust).mockResolvedValue(trust);
    vi.mocked(listLearningFeedback).mockResolvedValue({ feedback: [], count: 0 });
    const onClose = vi.fn();

    render(<OverviewModal onClose={onClose} />);

    // The project intro.
    expect(
      screen.getByText(/held accountable by evals/i),
    ).toBeInTheDocument();

    // Both reports render together — no tab switching.
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /How DietTrace stays accurate/i }),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByRole("heading", { name: /How much to trust your numbers/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("tab")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on Escape", () => {
    vi.mocked(getAccuracy).mockResolvedValue(accuracy);
    vi.mocked(getTrust).mockResolvedValue(trust);
    vi.mocked(listLearningFeedback).mockResolvedValue({ feedback: [], count: 0 });
    const onClose = vi.fn();
    render(<OverviewModal onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
