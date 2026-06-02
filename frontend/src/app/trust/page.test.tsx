import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import TrustPage from "@/app/trust/page";
import { getTrust, type TrustReport } from "@/lib/api";

vi.mock("@/lib/api", () => ({ getTrust: vi.fn() }));

const report: TrustReport = {
  count: 12,
  mean_confidence: 0.82,
  needs_review_pct: 0.25,
  source_breakdown: { usda: 8, web: 2 },
  recent_low_confidence: [
    {
      text: "a mystery dish",
      confidence: 0.41,
      review_reason: "couldn't resolve the portion",
      created_at: "2026-06-01T12:00:00+00:00",
    },
  ],
};

describe("TrustPage", () => {
  it("renders the headline confidence, % flagged, source breakdown, and recent flagged logs", async () => {
    vi.mocked(getTrust).mockResolvedValue(report);

    render(<TrustPage />);

    await waitFor(() =>
      expect(screen.getByText(/How much to trust/i)).toBeInTheDocument(),
    );
    expect(screen.getByText("82%")).toBeInTheDocument(); // mean confidence headline
    expect(screen.getByText("25%")).toBeInTheDocument(); // % flagged
    // Source breakdown bar names each source.
    expect(screen.getByText(/usda/i)).toBeInTheDocument();
    expect(screen.getByText(/web/i)).toBeInTheDocument();
    // The recent low-confidence list shows the meal text + its reason.
    expect(screen.getByText("a mystery dish")).toBeInTheDocument();
    expect(
      screen.getByText(/couldn't resolve the portion/i),
    ).toBeInTheDocument();
  });

  it("shows a calm empty state when nothing has been logged yet", async () => {
    vi.mocked(getTrust).mockResolvedValue({
      count: 0,
      mean_confidence: 0,
      needs_review_pct: 0,
      source_breakdown: {},
      recent_low_confidence: [],
    });

    render(<TrustPage />);

    await waitFor(() =>
      expect(screen.getByText(/Nothing logged yet/i)).toBeInTheDocument(),
    );
  });
});
