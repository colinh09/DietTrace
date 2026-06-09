import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OverviewModal } from "@/components/observability-modal";
import { HOW_STEPS } from "@/components/how-it-works";
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
  it("shows the accuracy report (the Trust section is gone)", async () => {
    vi.mocked(getAccuracy).mockResolvedValue(accuracy);
    const onClose = vi.fn();

    render(<OverviewModal onClose={onClose} />);

    expect(screen.getByText(/graded on accuracy/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /How DietTrace stays accurate/i }),
      ).toBeInTheDocument(),
    );
    // "How much to trust your numbers" was removed.
    expect(
      screen.queryByRole("heading", { name: /How much to trust your numbers/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("has a 'How it works' tab with the written guide and launches the tour", async () => {
    vi.mocked(getAccuracy).mockResolvedValue(accuracy);
    const onStartTour = vi.fn();
    render(<OverviewModal onClose={vi.fn()} onStartTour={onStartTour} />);

    // Defaults to the Accuracy report.
    await waitFor(() =>
      expect(
        screen.getByRole("heading", { name: /How DietTrace stays accurate/i }),
      ).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("tab", { name: /how it works/i }));
    expect(screen.getByText(HOW_STEPS[0].title)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /take the tour/i }));
    expect(onStartTour).toHaveBeenCalledTimes(1);
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
