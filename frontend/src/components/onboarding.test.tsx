import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Onboarding } from "@/components/onboarding";
import {
  postMacrosPlan,
  postMacrosSave,
  seedDemo,
  setProfile,
} from "@/lib/api";
import { markOnboarded } from "@/lib/onboarding";

vi.mock("@/lib/api", () => ({
  postMacrosPlan: vi.fn(),
  postMacrosSave: vi.fn(),
  seedDemo: vi.fn(),
  setProfile: vi.fn(),
  DEMO_PERSONAS: [
    { key: "runner", label: "Endurance runner", blurb: "carbs" },
    { key: "bodybuilder", label: "Bodybuilder", blurb: "protein" },
  ],
}));
vi.mock("@/lib/onboarding", () => ({ markOnboarded: vi.fn() }));
vi.mock("@/lib/setup", () => ({
  setSetup: vi.fn(),
  PERSONA_INPUTS: { runner: { sex: "female", weight_kg: 57 }, bodybuilder: {} },
}));

const plan = {
  targets: { "208": 2200, "203": 150, "205": 250, "204": 70 },
  rationale: "Sample plan.",
  source: "formula" as const,
  steps: [],
  clamped: [],
  eval: null,
  personalized: false,
  adherence: null,
};

describe("Onboarding (conversational)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(postMacrosPlan).mockResolvedValue(plan);
    vi.mocked(postMacrosSave).mockResolvedValue({
      ok: true,
      user: "u",
      targets: plan.targets,
      banked: false,
    });
    vi.mocked(setProfile).mockResolvedValue({ ok: true, profile_text: "x" });
    vi.mocked(seedDemo).mockResolvedValue({
      seeded: true,
      meals: 4,
      meal_date: "2026-06-07",
      dataset_date: "2026-06-06",
      goals_set: true,
      confirmations: 5,
      corrections: 2,
      persona: {
        key: "runner",
        label: "Endurance runner",
        blurb: "Carbs up big before runs.",
        goal_rationale: "Sample targets.",
        hook_meal: "spaghetti",
        hook_note: "The spaghetti logged low.",
        learns: "her pre-run carbs run high",
        meal_texts: ["a big plate of spaghetti"],
        confirmation_texts: ["oatmeal before a run"],
        correction_texts: ["I carb up more before runs"],
      },
    });
  });

  it("first screen shows the two choices", () => {
    render(<Onboarding onDone={vi.fn()} />);
    expect(screen.getByRole("button", { name: /see it in action/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /set up your own/i })).toBeInTheDocument();
  });

  it("'See it in action' goes straight into the detailed persona chooser, then lands", async () => {
    const onDone = vi.fn();
    render(<Onboarding onDone={onDone} />);
    // No intermediate sub-choice — clicking seeds the default persona directly.
    fireEvent.click(screen.getByRole("button", { name: /see it in action/i }));

    // Seeds against the user's LOCAL today (an ISO date), not the server's UTC date.
    await waitFor(() =>
      expect(seedDemo).toHaveBeenCalledWith(
        expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        "runner",
      ),
    );
    expect(markOnboarded).toHaveBeenCalledTimes(1);
    expect(onDone).not.toHaveBeenCalled();

    // The detailed chooser (SeededModal, with the persona switcher) is shown.
    expect(
      await screen.findByRole("heading", { name: "Endurance runner" }),
    ).toBeInTheDocument();

    // Closing the preview ("Got it") lands on the app.
    fireEvent.click(screen.getByRole("button", { name: /got it/i }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it("'Set up your own' runs the guided chat, then computes targets + saves the lifestyle", async () => {
    const onDone = vi.fn();
    render(<Onboarding onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: /set up your own/i }));

    // Q1 gender (chips) — the agent's first question is shown.
    expect(screen.getByText(/what's your gender/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Male" }));

    // Q2 weight (number input) — type a value and send.
    const weight = await screen.findByLabelText(/what do you weigh/i);
    fireEvent.change(weight, { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // Q3 age, Q4 height — skip both.
    fireEvent.click(await screen.findByRole("button", { name: /^skip$/i }));
    fireEvent.click(await screen.findByRole("button", { name: /^skip$/i }));

    // Q5 activity, Q6 goal — tap answers.
    fireEvent.click(await screen.findByRole("button", { name: "Moderately" }));
    fireEvent.click(await screen.findByRole("button", { name: "Maintain" }));

    // Q7 lifestyle (freeform) → Finish.
    const box = await screen.findByLabelText(/lifestyle, eating habits and goals/i);
    fireEvent.change(box, { target: { value: "Marathon training, high carb" } });
    fireEvent.click(screen.getByRole("button", { name: /finish/i }));

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(postMacrosPlan).toHaveBeenCalledWith(
      expect.objectContaining({ sex: "male", weight_kg: 75, goal: "maintain", ai_help: false }),
    );
    expect(postMacrosSave).toHaveBeenCalled();
    expect(setProfile).toHaveBeenCalledWith("Marathon training, high carb");
    expect(markOnboarded).toHaveBeenCalledTimes(1);
  });

  it("converts imperial units (lbs, ft/in) to kg/cm", async () => {
    const onDone = vi.fn();
    render(<Onboarding onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: /set up your own/i }));

    fireEvent.click(screen.getByRole("button", { name: "Male" }));

    // Weight in lbs: 165 lb → 75 kg.
    await screen.findByLabelText(/what do you weigh/i);
    fireEvent.click(screen.getByRole("button", { name: "lbs" }));
    fireEvent.change(screen.getByLabelText(/what do you weigh/i), {
      target: { value: "165" },
    });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // Age: skip.
    fireEvent.click(await screen.findByRole("button", { name: /^skip$/i }));

    // Height in ft/in: 5'10" → 178 cm.
    await screen.findByText(/your height/i);
    fireEvent.click(screen.getByRole("button", { name: "ft / in" }));
    fireEvent.change(screen.getByLabelText("feet"), { target: { value: "5" } });
    fireEvent.change(screen.getByLabelText("inches"), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    // Activity, goal, lifestyle-skip → finish.
    fireEvent.click(await screen.findByRole("button", { name: "Moderately" }));
    fireEvent.click(await screen.findByRole("button", { name: "Maintain" }));
    fireEvent.click(await screen.findByRole("button", { name: /^skip$/i }));

    await waitFor(() => expect(postMacrosPlan).toHaveBeenCalled());
    expect(postMacrosPlan).toHaveBeenCalledWith(
      expect.objectContaining({ weight_kg: 75, height_cm: 178 }),
    );
  });

  it("a fully-skipped chat still finishes with default targets", async () => {
    const onDone = vi.fn();
    render(<Onboarding onDone={onDone} />);
    fireEvent.click(screen.getByRole("button", { name: /set up your own/i }));

    // Skip every question (gender, weight, age, height, activity, goal).
    for (let i = 0; i < 6; i++) {
      fireEvent.click(await screen.findByRole("button", { name: /^skip$/i }));
    }
    // Lifestyle skipped too.
    fireEvent.click(await screen.findByRole("button", { name: /^skip$/i }));

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    // Defaults still produce a plan; no profile text was set.
    expect(postMacrosPlan).toHaveBeenCalledWith(
      expect.objectContaining({ sex: "male", ai_help: false }),
    );
    expect(setProfile).not.toHaveBeenCalled();
    expect(markOnboarded).toHaveBeenCalledTimes(1);
  });
});
