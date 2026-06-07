import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SetupDetailsButton } from "@/components/setup-details-button";
import {
  getGoals,
  getPreferences,
  getProfile,
  getTrust,
  listLearningFeedback,
} from "@/lib/api";
import { getSetup } from "@/lib/setup";

vi.mock("@/lib/setup", () => ({ getSetup: vi.fn() }));
vi.mock("@/lib/api", () => ({
  getGoals: vi.fn(),
  getPreferences: vi.fn(),
  getProfile: vi.fn(),
  getTrust: vi.fn(),
  listLearningFeedback: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getGoals).mockResolvedValue({
    goals: [
      { code: "208", name: "Energy", target: 2000, unit: "kcal" },
      { code: "203", name: "Protein", target: 150, unit: "g" },
      { code: "205", name: "Carbohydrate", target: 200, unit: "g" },
      { code: "204", name: "Fat", target: 60, unit: "g" },
    ],
  });
  vi.mocked(getPreferences).mockResolvedValue({
    block: null,
    corrections: 0,
    new_corrections: 0,
    confirmations: 0,
    confirmed: [],
    min_corrections: 1,
  });
  vi.mocked(getProfile).mockResolvedValue({ profile_text: "" });
  vi.mocked(getTrust).mockResolvedValue({
    count: 0,
    mean_confidence: 0,
    needs_review_pct: 0,
    source_breakdown: {},
    recent_low_confidence: [],
  });
  vi.mocked(listLearningFeedback).mockResolvedValue({ feedback: [], count: 0 });
});

describe("SetupDetailsButton", () => {
  it("recaps the user's own setup (body stats + targets, no switcher)", async () => {
    vi.mocked(getProfile).mockResolvedValue({
      profile_text: "Marathon training, plant-based",
    });
    vi.mocked(getSetup).mockReturnValue({
      kind: "own",
      inputs: { sex: "female", weight_kg: 60, activity: "very_active", goal: "cut" },
      lifestyle: "Marathon training, plant-based",
    });
    render(<SetupDetailsButton />);
    fireEvent.click(screen.getByRole("button", { name: /persona details/i }));

    expect(screen.getByRole("heading", { name: "About you" })).toBeInTheDocument();
    expect(screen.getByText("Female")).toBeInTheDocument();
    expect(screen.getByText("60 kg")).toBeInTheDocument();
    expect(screen.getByText("Very active")).toBeInTheDocument();
    expect(screen.getByText("Daily targets")).toBeInTheDocument();
    // No persona switcher — only one heading, no "Bodybuilder" option.
    expect(screen.queryByText("Bodybuilder")).not.toBeInTheDocument();
    // Lifestyle (from /profile) shows once it resolves.
    expect(
      await screen.findByText(/marathon training, plant-based/i),
    ).toBeInTheDocument();
  });

  it("recaps a seeded demo persona (read-only, no switcher)", () => {
    vi.mocked(getSetup).mockReturnValue({
      kind: "persona",
      personaKey: "runner",
      inputs: {},
      result: {
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
          goal_rationale: "x",
          hook_meal: "spaghetti",
          hook_note: "low",
          learns: "carbs run high",
          meal_texts: ["a big plate of spaghetti"],
          confirmation_texts: ["oatmeal before a run"],
          correction_texts: ["I carb up more"],
        },
      },
    });
    render(<SetupDetailsButton />);
    fireEvent.click(screen.getByRole("button", { name: /persona details/i }));

    expect(
      screen.getByRole("heading", { name: "Endurance runner" }),
    ).toBeInTheDocument();
    // It's the recap, not the onboarding explainer with the switcher.
    expect(screen.queryByText(/on today — your playground/i)).not.toBeInTheDocument();
  });

  it("handles no setup yet", () => {
    vi.mocked(getSetup).mockReturnValue(null);
    render(<SetupDetailsButton />);
    fireEvent.click(screen.getByRole("button", { name: /persona details/i }));
    expect(screen.getByText(/nothing set up yet/i)).toBeInTheDocument();
  });
});
