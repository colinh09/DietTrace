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
    // Corrections are collapsed by default — expand the section first.
    fireEvent.click(await screen.findByRole("button", { name: /your corrections/i }));
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

  it("auto-runs the gated retune on a new signal and hands the outcome to the page", async () => {
    // Retunes are agent-driven now (no manual button) — a new supervisor signal
    // (autoRetune increment) fires the stream; the outcome goes to the feed.
    vi.mocked(api.learningRetuneStream).mockImplementation(async (onEvent) => {
      onEvent({ type: "phase", phase: "propose", label: "Suggesting a change…" });
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
    const onComplete = vi.fn();
    const { rerender } = render(
      <LearningObservability reloadSignal={0} autoRetune={0} onRetuneComplete={onComplete} />,
    );
    rerender(
      <LearningObservability reloadSignal={0} autoRetune={1} onRetuneComplete={onComplete} />,
    );

    await waitFor(() => expect(api.learningRetuneStream).toHaveBeenCalled());
    await waitFor(() =>
      expect(onComplete).toHaveBeenCalledWith(
        expect.objectContaining({ op: "retune" }),
        true,
        1,
      ),
    );
  });

  it("streams the new rule + status live, but no premature score panels", async () => {
    // The live view (in the rail) is status + the new rule only — the per-meal
    // panels appear in the collapsible results AFTER, not as a half-baked preview.
    let finish: () => void = () => {};
    vi.mocked(api.learningRetuneStream).mockImplementation(async (onEvent) => {
      onEvent({ type: "phase", phase: "fit", label: "Running an experiment in Phoenix…" });
      onEvent({ type: "rule", rules: [{ rule: "Pre-run carbs run high", rationale: "x", from_feedback: [1] }] });
      onEvent({
        type: "manifest",
        rows: [
          { set: "fit", text: "oatmeal before my long run" },
          { set: "usda", text: "a medium banana" },
        ],
      });
      await new Promise<void>((r) => { finish = r; });
    });
    const { rerender } = render(<LearningObservability reloadSignal={0} autoRetune={0} />);
    rerender(<LearningObservability reloadSignal={0} autoRetune={1} />);

    await waitFor(() =>
      expect(screen.getByText(/Pre-run carbs run high/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Running an experiment in Phoenix/)).toBeInTheDocument();
    expect(screen.queryAllByText("Base")).toHaveLength(0);
    expect(screen.queryByText("a medium banana")).not.toBeInTheDocument();
    finish();
  });

  it("force-retunes from the rail header via the confirm modal", async () => {
    vi.mocked(api.learningRetuneStream).mockImplementation(async () => {});
    render(<LearningObservability reloadSignal={0} />);

    // The rail button enables once a correction is banked (new_corrections=1).
    const railBtn = await screen.findByRole("button", { name: /retune now/i });
    await waitFor(() => expect(railBtn).not.toBeDisabled());
    fireEvent.click(railBtn);

    // The confirm modal opens; confirming fires the retune (no auto-threshold).
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("heading", { name: /retune diettrace now/i }),
    ).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /retune now/i }));
    await waitFor(() => expect(api.learningRetuneStream).toHaveBeenCalled());
  });

  it("disables the rail retune button when nothing new is banked", async () => {
    vi.mocked(api.getPreferences).mockResolvedValue({
      block: null, corrections: 2, new_corrections: 0, confirmations: 3,
      confirmed, min_corrections: 1,
    });
    render(<LearningObservability reloadSignal={0} />);
    const railBtn = await screen.findByRole("button", { name: /retune now/i });
    await waitFor(() => expect(railBtn).toBeDisabled());
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

  it("expands the test set", async () => {
    await openState();
    const toggle = await screen.findByRole("button", { name: /your dataset/i });
    expect(screen.queryByText(/oatmeal before my long run/)).not.toBeInTheDocument();
    fireEvent.click(toggle);
    const list = screen.getByText(/oatmeal before my long run/);
    expect(list).toBeInTheDocument();
    expect(within(list.closest("li") as HTMLElement).getByText(/520 kcal/)).toBeInTheDocument();
  });
});
