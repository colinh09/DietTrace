import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MacroModal } from "@/components/macro-modal";
import { postMacrosSave } from "@/lib/api";

vi.mock("@/lib/api", () => ({ postMacrosSave: vi.fn() }));

const GOALS = [
  { code: "208", name: "Energy", target: 2000, unit: "kcal", consumed: 0, remaining: 2000 },
  { code: "203", name: "Protein", target: 150, unit: "g", consumed: 0, remaining: 150 },
  { code: "205", name: "Carb", target: 200, unit: "g", consumed: 0, remaining: 200 },
  { code: "204", name: "Fat", target: 60, unit: "g", consumed: 0, remaining: 60 },
];

describe("MacroModal", () => {
  beforeEach(() => vi.clearAllMocks());

  it("quick-edits the current targets and flags a calorie mismatch", async () => {
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

  it("'Recalculate from your details' hands off to the onboarding chat", () => {
    const onRecalc = vi.fn();
    render(<MacroModal goals={GOALS} onClose={vi.fn()} onRecalc={onRecalc} />);
    fireEvent.click(
      screen.getByRole("button", { name: /recalculate from your details/i }),
    );
    expect(onRecalc).toHaveBeenCalledTimes(1);
  });
});
