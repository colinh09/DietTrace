import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "@/components/dashboard";
import * as api from "@/lib/api";

// The Dashboard hosts the agent-activity feed + the state modal (which fetches
// the learning state on mount) — stub those reads.
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
    block: null, corrections: 0, new_corrections: 0, confirmations: 0,
    confirmations_custom: 0, confirmations_seeded: 0, confirmed: [], min_corrections: 1,
  });
  vi.mocked(api.listLearningFeedback).mockResolvedValue({ feedback: [], count: 0 });
  vi.mocked(api.getProfile).mockResolvedValue({ profile_text: "" });
  vi.mocked(api.setProfile).mockResolvedValue({ ok: true, profile_text: "" });
});

describe("Dashboard", () => {
  it("renders the agent-activity rail with a state button", () => {
    render(<Dashboard reloadSignal={0} />);
    expect(screen.getByText(/watching your diet log/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /agent state/i }),
    ).toBeInTheDocument();
  });

  it("shows the supervisor's per-meal decisions in the feed", () => {
    render(
      <Dashboard
        reloadSignal={0}
        agentEvents={[
          { id: 1, op: "add_dataset_point", reason: "clean meal", mealText: "two eggs", when: "now" },
        ]}
      />,
    );
    expect(screen.getByText("two eggs")).toBeInTheDocument();
    expect(screen.getByText(/added to your dataset/i)).toBeInTheDocument();
  });

  it("opens the agent-state modal from the icon", async () => {
    render(<Dashboard reloadSignal={0} />);
    fireEvent.click(screen.getByRole("button", { name: /agent state/i }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
    expect(screen.getByText(/meals in your dataset/i)).toBeInTheDocument();
  });
});
