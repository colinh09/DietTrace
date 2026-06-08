import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MacroModal } from "@/components/macro-modal";
import { postMacrosSave } from "@/lib/api";
import { getSetup } from "@/lib/setup";

vi.mock("@/lib/api", () => ({
  postMacrosPlan: vi.fn(),
  postMacrosSave: vi.fn(),
}));

const GOALS = [
  { code: "208", name: "Energy", target: 2000, unit: "kcal", consumed: 0, remaining: 2000 },
  { code: "203", name: "Protein", target: 150, unit: "g", consumed: 0, remaining: 150 },
  { code: "205", name: "Carb", target: 200, unit: "g", consumed: 0, remaining: 200 },
  { code: "204", name: "Fat", target: 60, unit: "g", consumed: 0, remaining: 60 },
];
vi.mock("@/lib/setup", () => ({ getSetup: vi.fn() }));

describe("MacroModal", () => {
  beforeEach(() => vi.clearAllMocks());

  it("prefills the form from the user's saved setup (not hardcoded defaults)", () => {
    vi.mocked(getSetup).mockReturnValue({
      kind: "own",
      inputs: {
        age: 29,
        sex: "female",
        height_cm: 168,
        weight_kg: 57,
        activity: "very_active",
        goal: "cut",
        preference: "carb up before runs",
      },
      lifestyle: "marathon training",
    });
    render(<MacroModal onClose={vi.fn()} />);

    expect(screen.getByDisplayValue("29")).toBeInTheDocument(); // age
    expect(screen.getByDisplayValue("168")).toBeInTheDocument(); // height
    expect(screen.getByDisplayValue("57")).toBeInTheDocument(); // weight
    expect(screen.getByDisplayValue("carb up before runs")).toBeInTheDocument();
    // Their gender choice is the selected segment.
    expect(screen.getByRole("button", { name: "Female" })).toHaveClass("on");
  });

  it("defaults to quick-edit with the current targets and flags a calorie mismatch", async () => {
    vi.mocked(getSetup).mockReturnValue(null);
    vi.mocked(postMacrosSave).mockResolvedValue({ ok: true } as never);
    render(<MacroModal goals={GOALS} onClose={vi.fn()} onSaved={vi.fn()} />);

    expect(screen.getByText("Your daily targets")).toBeInTheDocument();
    // 150*4 + 200*4 + 60*9 = 1,940 vs a 2,000 target → 60 under.
    expect(screen.getByText(/1,940 kcal/)).toBeInTheDocument();
    expect(screen.getByText(/under your 2,000 kcal target/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /save targets/i }));
    await waitFor(() =>
      expect(postMacrosSave).toHaveBeenCalledWith(
        { "208": 2000, "203": 150, "205": 200, "204": 60 },
        null,
        "manual",
      ),
    );
  });

  it("falls back to blanks when there's no setup (no made-up numbers)", () => {
    vi.mocked(getSetup).mockReturnValue(null);
    render(<MacroModal onClose={vi.fn()} />);
    // The old hardcoded "31" / "keep protein high" are gone.
    expect(screen.queryByDisplayValue("31")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("keep protein high")).not.toBeInTheDocument();
  });
});
