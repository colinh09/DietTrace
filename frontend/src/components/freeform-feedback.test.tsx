import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FreeformFeedback } from "@/components/freeform-feedback";
import { submitFreeformFeedback } from "@/lib/api";

vi.mock("@/lib/api", () => ({ submitFreeformFeedback: vi.fn(), userId: () => "test" }));

beforeEach(() => vi.clearAllMocks());

const _ok = (kind: string, target: string, adj: number | null, pref = false) => ({
  ok: true,
  applied: kind !== "standing_rule",
  kind,
  target_food: target,
  adjustment: adj,
  rationale: "test rationale",
  scope: "this_food",
  stored_as_preference: pref,
  per_item: [],
  totals: [],
  added_to_arize: false,
  phoenix_url: "",
});

describe("FreeformFeedback", () => {
  it("renders a text input and a 'tell it' button", () => {
    render(<FreeformFeedback />);
    expect(screen.getByRole("textbox", { name: /free-form feedback/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /tell it/i })).toBeInTheDocument();
  });

  it("disables the button while loading", async () => {
    let resolve!: (v: ReturnType<typeof _ok>) => void;
    const pending = new Promise<ReturnType<typeof _ok>>((r) => { resolve = r; });
    vi.mocked(submitFreeformFeedback).mockReturnValue(pending);

    render(<FreeformFeedback mealId={1} mealText="fries" perItem={[]} />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "half the fries" } });
    fireEvent.click(screen.getByRole("button", { name: /tell it/i }));

    await waitFor(() => expect(screen.getByRole("button")).toBeDisabled());
    resolve(_ok("portion_adjust", "fries", 0.5));
  });

  it("shows 'DietTrace learned' panel after a successful portion_adjust", async () => {
    vi.mocked(submitFreeformFeedback).mockResolvedValue(
      _ok("portion_adjust", "fries", 0.5),
    );

    render(<FreeformFeedback mealId={1} mealText="fries" perItem={[]} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "fries were half" } });
    fireEvent.click(screen.getByRole("button", { name: /tell it/i }));

    await waitFor(() => {
      expect(screen.getByText(/DietTrace learned/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/scaled fries to 50% of the logged portion/i)).toBeInTheDocument();
  });

  it("labels an absolute-grams fix as 'set … to N g', not a percentage", async () => {
    vi.mocked(submitFreeformFeedback).mockResolvedValue({
      ..._ok("portion_adjust", "peanut butter", null),
      target_grams: 30,
    });

    render(<FreeformFeedback mealId={1} mealText="pb on apple" perItem={[]} />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "I only eat about 30 grams of peanut butter" },
    });
    fireEvent.click(screen.getByRole("button", { name: /tell it/i }));

    await waitFor(() => {
      expect(screen.getByText(/set peanut butter to 30 g/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/% of the logged portion/i)).not.toBeInTheDocument();
  });

  it("shows standing-preference note for a standing_rule result", async () => {
    vi.mocked(submitFreeformFeedback).mockResolvedValue(
      _ok("standing_rule", "preworkout", 80, true),
    );

    render(<FreeformFeedback mealId={1} mealText="fries" perItem={[]} />);
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "from now on aim for 80g carbs" },
    });
    fireEvent.click(screen.getByRole("button", { name: /tell it/i }));

    await waitFor(() => {
      expect(screen.getByText(/DietTrace learned/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/test rationale/i)).toBeInTheDocument();
    expect(
      screen.getByText(/standing rule — DietTrace applies it to your future meals/i),
    ).toBeInTheDocument();
  });

  it("shows an error message when the API call fails", async () => {
    vi.mocked(submitFreeformFeedback).mockRejectedValue(new Error("network error"));

    render(<FreeformFeedback mealId={1} mealText="fries" perItem={[]} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "half fries" } });
    fireEvent.click(screen.getByRole("button", { name: /tell it/i }));

    await waitFor(() => {
      expect(screen.getByText(/couldn't apply/i)).toBeInTheDocument();
    });
  });

  it("calls onFeedbackApplied with the result on success", async () => {
    const result = _ok("remove_item", "cheese", null);
    vi.mocked(submitFreeformFeedback).mockResolvedValue(result);
    const onApplied = vi.fn();

    render(
      <FreeformFeedback mealId={1} mealText="fries" perItem={[]} onFeedbackApplied={onApplied} />,
    );
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "no cheese" } });
    fireEvent.click(screen.getByRole("button", { name: /tell it/i }));

    await waitFor(() => expect(onApplied).toHaveBeenCalledWith(result));
  });

  it("does not call API when the input is empty", () => {
    render(<FreeformFeedback />);
    fireEvent.click(screen.getByRole("button", { name: /tell it/i }));
    expect(submitFreeformFeedback).not.toHaveBeenCalled();
  });
});
