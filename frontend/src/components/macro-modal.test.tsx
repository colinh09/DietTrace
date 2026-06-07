import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MacroModal } from "@/components/macro-modal";
import { getSetup } from "@/lib/setup";

vi.mock("@/lib/api", () => ({
  postMacrosPlan: vi.fn(),
  postMacrosSave: vi.fn(),
}));
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

  it("falls back to blanks when there's no setup (no made-up numbers)", () => {
    vi.mocked(getSetup).mockReturnValue(null);
    render(<MacroModal onClose={vi.fn()} />);
    // The old hardcoded "31" / "keep protein high" are gone.
    expect(screen.queryByDisplayValue("31")).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("keep protein high")).not.toBeInTheDocument();
  });
});
