import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ObservabilityModal } from "@/components/observability-modal";
import { getAccuracy, getTrust, type AccuracyReport, type TrustReport } from "@/lib/api";

vi.mock("@/lib/api", () => ({ getAccuracy: vi.fn(), getTrust: vi.fn() }));

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

describe("ObservabilityModal", () => {
  it("opens on the requested tab, switches tabs, and closes", async () => {
    vi.mocked(getAccuracy).mockResolvedValue(accuracy);
    vi.mocked(getTrust).mockResolvedValue(trust);
    const onClose = vi.fn();

    render(<ObservabilityModal initialTab="accuracy" onClose={onClose} />);

    // Accuracy content loads.
    await waitFor(() =>
      expect(screen.getByText(/How DietTrace stays accurate/i)).toBeInTheDocument(),
    );

    // Switch to the trust tab.
    fireEvent.click(screen.getByRole("tab", { name: /trust/i }));
    await waitFor(() =>
      expect(screen.getByText(/How much to trust your numbers/i)).toBeInTheDocument(),
    );

    // Close via the ✕.
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on Escape", async () => {
    vi.mocked(getAccuracy).mockResolvedValue(accuracy);
    vi.mocked(getTrust).mockResolvedValue(trust);
    const onClose = vi.fn();
    render(<ObservabilityModal initialTab="trust" onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});
