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
  it("asks 'does this look right?' with two paths (looks right / something's off)", () => {
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);
    expect(screen.getByText(/does this look right/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /looks right/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /something's off/i })).toBeInTheDocument();
    // The correction box only shows once a path is chosen.
    expect(screen.queryByLabelText(/free-form feedback/i)).not.toBeInTheDocument();
  });

  it("confirms the meal as a held-out reference on 'looks right'", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));
    await waitFor(() =>
      expect(api.confirmMeal).toHaveBeenCalledWith("oatmeal", perItem, totals),
    );
    expect(await screen.findByText(/held-out reference/i)).toBeInTheDocument();
  });

  it("reveals the correction box on 'something's off'", () => {
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);
    fireEvent.click(screen.getByRole("button", { name: /something's off/i }));
    expect(screen.getByLabelText(/free-form feedback/i)).toBeInTheDocument();
  });

  it("offers a portion nudge after confirming, opening the quantity editor", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));
    fireEvent.click(await screen.findByRole("button", { name: /nudge a portion/i }));
    // The gram editor opens with the item's editable grams.
    expect(screen.getByLabelText(/grams of oats/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save as reference/i }));
    await waitFor(() => expect(api.confirmMeal).toHaveBeenCalled());
    expect(await screen.findByText(/held-out reference/i)).toBeInTheDocument();
  });

  it("offers a path back to correcting after confirming (XOR)", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));
    await screen.findByText(/held-out reference/i);
    fireEvent.click(screen.getByRole("button", { name: /actually, something's off/i }));
    expect(screen.getByLabelText(/free-form feedback/i)).toBeInTheDocument();
  });
});
