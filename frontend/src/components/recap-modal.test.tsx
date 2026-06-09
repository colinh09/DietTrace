import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { RecapModal } from "@/components/recap-modal";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getGoals: vi.fn(),
  getPreferences: vi.fn(),
  getProfile: vi.fn(),
  getTrust: vi.fn(),
  listLearningFeedback: vi.fn(),
  setProfile: vi.fn(),
}));

const setup = { kind: "own", inputs: { sex: "male" } } as never;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getGoals).mockResolvedValue({ goals: [] });
  vi.mocked(api.getPreferences).mockResolvedValue({
    block: null, corrections: 0, new_corrections: 0, confirmations: 0,
    confirmed: [], min_corrections: 1,
  } as never);
  vi.mocked(api.getProfile).mockResolvedValue({ profile_text: "" });
  vi.mocked(api.getTrust).mockResolvedValue({ count: 0, mean_confidence: 0 } as never);
  vi.mocked(api.listLearningFeedback).mockResolvedValue({ feedback: [], count: 0 });
});

describe("RecapModal", () => {
  it("lets you add a context note when there's none (an editable empty box)", async () => {
    vi.mocked(api.setProfile).mockResolvedValue({
      ok: true, profile_text: "marathon training, plant-based",
    });
    render(<RecapModal setup={setup} onClose={vi.fn()} />);

    // With no note, the section offers "Add" (not just a 'go elsewhere' message).
    fireEvent.click(await screen.findByRole("button", { name: /^add$/i }));

    const box = screen.getByLabelText(/your goals and eating style/i);
    fireEvent.change(box, { target: { value: "marathon training, plant-based" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() =>
      expect(api.setProfile).toHaveBeenCalledWith("marathon training, plant-based"),
    );
  });
});
