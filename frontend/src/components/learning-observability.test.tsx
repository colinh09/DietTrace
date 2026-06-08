import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LearningObservability } from "@/components/learning-observability";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getPreferences: vi.fn(),
  listLearningFeedback: vi.fn(),
  learningRetuneStream: vi.fn(),
  editLearningFeedback: vi.fn(),
  deleteLearningFeedback: vi.fn(),
  getProfile: vi.fn(),
  setProfile: vi.fn(),
}));

const feedback = [
  {
    id: 1,
    created_at: "x",
    feedback_text: "before a run I carb up way more than this",
    meal_text: "a big plate of spaghetti",
    weight: 2,
    processed: false,
  },
];

const confirmed = [
  { id: 11, meal_text: "oatmeal before my long run", calories: 520 },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getPreferences).mockResolvedValue({
    block: null, corrections: 1, new_corrections: 1, confirmations: 1, confirmed, min_corrections: 1,
  });
  vi.mocked(api.listLearningFeedback).mockResolvedValue({ feedback, count: 1 });
  vi.mocked(api.getProfile).mockResolvedValue({ profile_text: "" });
  vi.mocked(api.setProfile).mockResolvedValue({ ok: true, profile_text: "" });
});

// The detail (corrections, re-tune, context, test set) now lives behind the state
// icon — render the panel and open the modal before asserting on that content.
async function openState() {
  render(<LearningObservability reloadSignal={0} />);
  fireEvent.click(await screen.findByRole("button", { name: /agent state/i }));
  await screen.findByRole("dialog");
}

describe("LearningObservability", () => {
  it("shows corrections as meal + what you said (persisted, not a bare count)", async () => {
    await openState();
    expect(await screen.findByText("a big plate of spaghetti")).toBeInTheDocument();
    expect(
      screen.getByText(/before a run I carb up way more/i),
    ).toBeInTheDocument();
  });

  it("refetches when the reload signal changes (corrections persist across nav)", async () => {
    const { rerender } = render(<LearningObservability reloadSignal={0} />);
    await waitFor(() => expect(api.listLearningFeedback).toHaveBeenCalledTimes(1));
    rerender(<LearningObservability reloadSignal={1} />);
    await waitFor(() => expect(api.listLearningFeedback).toHaveBeenCalledTimes(2));
  });

  it("streams the re-tune live — phase, rule, per-meal scores, then verdict", async () => {
    vi.mocked(api.learningRetuneStream).mockImplementation(async (onEvent) => {
      onEvent({ type: "phase", phase: "propose", label: "Generalizing your corrections…" });
      onEvent({ type: "rule", rules: [{ rule: "Pre-run carbs run high", rationale: "x", from_feedback: [1] }] });
      onEvent({ type: "score", set: "fit", i: 1, n: 1, text: "oatmeal before my long run", expected: 520, before: 0.6, after: 0.9 });
      onEvent({
        type: "done", ok: true, shipped: true,
        verdict: { ship: true, usda_ok: true, fit_gain: true, reason: "fit 60% → 90%", eps: 0.05 },
        current: { usda: 0.78, fit: 0.6 }, proposed: { usda: 0.78, fit: 0.9 },
        rules: [{ rule: "Pre-run carbs run high", rationale: "x", from_feedback: [1] }],
        version: 1, fit_cases: 1, usda_cases: 2,
      });
    });
    await openState();
    fireEvent.click(await screen.findByRole("button", { name: /re-tune/i }));

    await waitFor(() => expect(screen.getByText(/Kept/)).toBeInTheDocument());
    expect(screen.getByText(/On your meals/)).toBeInTheDocument();
    expect(screen.getAllByText(/90%/).length).toBeGreaterThan(0);
  });

  it("lists the full eval set up front and fills rows as scores stream", async () => {
    let finish: () => void = () => {};
    vi.mocked(api.learningRetuneStream).mockImplementation(async (onEvent) => {
      onEvent({ type: "phase", phase: "fit", label: "Re-scoring your meals…" });
      onEvent({
        type: "manifest",
        rows: [
          { set: "fit", text: "oatmeal before my long run" },
          { set: "usda", text: "a medium banana" },
        ],
      });
      onEvent({ type: "score", set: "fit", i: 1, n: 1, text: "oatmeal before my long run", expected: 520, before: 0.6, after: 0.9 });
      await new Promise<void>((r) => { finish = r; });
    });
    await openState();
    fireEvent.click(await screen.findByRole("button", { name: /re-tune/i }));

    await waitFor(() =>
      expect(screen.getByText("a medium banana")).toBeInTheDocument(),
    );
    expect(screen.getByText("oatmeal before my long run")).toBeInTheDocument();
    // Two side-by-side panels (Fit to you · USDA), each with Base/Tuned columns.
    expect(screen.getAllByText("Base")).toHaveLength(2);
    expect(screen.getAllByText("Tuned")).toHaveLength(2);
    finish();
  });

  it("shows the user's context (the corrector's standing profile) and lets them edit it", async () => {
    vi.mocked(api.getProfile).mockResolvedValue({
      profile_text: "Marathon training, mostly plant-based",
    });
    vi.mocked(api.setProfile).mockResolvedValue({
      ok: true,
      profile_text: "Marathon training, eats high carb",
    });
    await openState();

    expect(
      await screen.findByText(/marathon training, mostly plant-based/i),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /edit/i }));
    const box = screen.getByLabelText(/your goals and eating style/i);
    fireEvent.change(box, { target: { value: "Marathon training, eats high carb" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() =>
      expect(api.setProfile).toHaveBeenCalledWith("Marathon training, eats high carb"),
    );
  });

  it("shows the fresh-corrections indicator from the backend threshold", async () => {
    vi.mocked(api.getPreferences).mockResolvedValue({
      block: null, corrections: 3, new_corrections: 0, confirmations: 2,
      confirmed, min_corrections: 1,
    });
    await openState();
    expect(await screen.findByText(/0 of 1 fresh correction/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /re-tune/i })).toBeDisabled();
  });

  it("expands the test set", async () => {
    await openState();
    const toggle = await screen.findByRole("button", { name: /test set/i });
    expect(screen.queryByText(/oatmeal before my long run/)).not.toBeInTheDocument();
    fireEvent.click(toggle);
    const list = screen.getByText(/oatmeal before my long run/);
    expect(list).toBeInTheDocument();
    expect(within(list.closest("li") as HTMLElement).getByText(/520 kcal/)).toBeInTheDocument();
  });
});
