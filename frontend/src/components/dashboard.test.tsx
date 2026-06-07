import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "@/components/dashboard";
import * as api from "@/lib/api";
import type { TraceStep } from "@/lib/api";

// The Dashboard now hosts the always-visible LearningObservability panel, which
// fetches the learning state on mount — stub those reads.
vi.mock("@/lib/api", () => ({
  getPreferences: vi.fn(),
  listLearningFeedback: vi.fn(),
  learningRetuneStream: vi.fn(),
  editLearningFeedback: vi.fn(),
  deleteLearningFeedback: vi.fn(),
  getProfile: vi.fn(),
  setProfile: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getPreferences).mockResolvedValue({
    block: null, corrections: 0, new_corrections: 0, confirmations: 0, confirmed: [], min_corrections: 1,
  });
  vi.mocked(api.listLearningFeedback).mockResolvedValue({ feedback: [], count: 0 });
  vi.mocked(api.getProfile).mockResolvedValue({ profile_text: "" });
  vi.mocked(api.setProfile).mockResolvedValue({ ok: true, profile_text: "" });
});

describe("Dashboard", () => {
  it("renders the observability rail with the learning panel", async () => {
    render(<Dashboard reloadSignal={0} latestTrace={null} />);
    expect(screen.getByText(/observability/i)).toBeInTheDocument();
    // The always-visible self-tuning panel is present (no modal).
    await waitFor(() => expect(screen.getByText(/self-tuning/i)).toBeInTheDocument());
    expect(screen.getByText(/tests itself on/i)).toBeInTheDocument();
  });

  it("surfaces the latest meal's agent trace", () => {
    const steps: TraceStep[] = [
      { step: "parse_meal", summary: "parsed" },
      { step: "search_nutrition", summary: "found" },
      { step: "estimate_portion", summary: "120 g" },
    ];
    render(<Dashboard reloadSignal={0} latestTrace={{ text: "a banana", steps }} />);

    expect(screen.getByText(/latest trace/i)).toBeInTheDocument();
    expect(screen.getByText("a banana")).toBeInTheDocument();
    expect(screen.getByText("parse_meal")).toBeInTheDocument();
    expect(screen.getByText("estimate_portion")).toBeInTheDocument();
  });
});
