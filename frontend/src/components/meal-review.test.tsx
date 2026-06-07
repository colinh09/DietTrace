import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MealReview } from "@/components/meal-review";
import * as api from "@/lib/api";

vi.mock("@/lib/api", () => ({
  confirmMeal: vi.fn(),
  submitFreeformFeedback: vi.fn(),
}));

const perItem = [
  { fdc_id: 1, description: "oats", grams: 80, nutrients: [] },
];
const totals = [{ code: "208", name: "Energy", amount: 300, unit: "kcal" }];

beforeEach(() => vi.clearAllMocks());

describe("MealReview", () => {
  it("asks 'does this look about right?' with three paths (yes / tweak / no)", () => {
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);
    expect(screen.getByText(/does this look about right/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /yes, looks right/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /tweak a portion/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /no, something's off/i })).toBeInTheDocument();
    // Neither the editor nor the correction box shows until a path is chosen.
    expect(screen.queryByLabelText(/free-form feedback/i)).not.toBeInTheDocument();
  });

  it("confirms the meal as a reference on 'yes, looks right'", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /yes, looks right/i }));
    await waitFor(() =>
      expect(api.confirmMeal).toHaveBeenCalledWith("oatmeal", perItem, totals),
    );
    expect(await screen.findByText(/saved as a reference/i)).toBeInTheDocument();
  });

  it("reveals the correction box on 'No, something's off'", () => {
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);
    fireEvent.click(screen.getByRole("button", { name: /no, something's off/i }));
    expect(screen.getByLabelText(/free-form feedback/i)).toBeInTheDocument();
  });

  it("opens the quantity editor on 'tweak a portion' and confirms the edited meal", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /tweak a portion/i }));
    // The gram editor is shown with the item's editable grams.
    const input = screen.getByLabelText(/grams of oats/i);
    expect(input).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save as reference/i }));
    await waitFor(() => expect(api.confirmMeal).toHaveBeenCalled());
    expect(await screen.findByText(/saved as a reference/i)).toBeInTheDocument();
  });

  it("offers a path back to correcting after confirming (XOR)", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /yes, looks right/i }));
    await screen.findByText(/saved as a reference/i);
    fireEvent.click(screen.getByRole("button", { name: /change something/i }));
    expect(screen.getByLabelText(/free-form feedback/i)).toBeInTheDocument();
  });
});
