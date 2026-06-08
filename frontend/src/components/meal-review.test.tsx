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

  it("'looks right' → 'would you change anything?' → confirm adds it to your dataset", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));
    // Intermediate step before anything is saved.
    expect(await screen.findByText(/would you change anything/i)).toBeInTheDocument();
    expect(api.confirmMeal).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /confirm it/i }));
    await waitFor(() =>
      expect(api.confirmMeal).toHaveBeenCalledWith("oatmeal", perItem, totals),
    );
    expect(await screen.findByText(/your dataset/i)).toBeInTheDocument();
  });

  it("an adjusted-portion confirm still reaches the feed (onAgentEvent + onCorrected)", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    const onAgentEvent = vi.fn();
    const onCorrected = vi.fn();
    render(
      <MealReview
        mealText="oatmeal"
        perItem={perItem}
        totals={totals}
        onAgentEvent={onAgentEvent}
        onCorrected={onCorrected}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));
    fireEvent.click(await screen.findByRole("button", { name: /adjust a portion/i }));
    fireEvent.click(screen.getByRole("button", { name: /save as confirmed/i }));
    // The adjust-portion path used to skip both of these — the meal never reached
    // the agent feed and never became a dataset point.
    await waitFor(() =>
      expect(onAgentEvent).toHaveBeenCalledWith(
        expect.objectContaining({ op: "add_dataset_point" }),
      ),
    );
    expect(onCorrected).toHaveBeenCalled();
  });

  it("reveals the correction box on 'something's off'", () => {
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);
    fireEvent.click(screen.getByRole("button", { name: /something's off/i }));
    expect(screen.getByLabelText(/free-form feedback/i)).toBeInTheDocument();
  });

  it("lets you adjust a portion at the 'change anything?' step before confirming", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));
    fireEvent.click(await screen.findByRole("button", { name: /adjust a portion/i }));
    // The gram editor opens with the item's editable grams.
    expect(screen.getByLabelText(/grams of oats/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /save as confirmed/i }));
    await waitFor(() => expect(api.confirmMeal).toHaveBeenCalled());
    expect(await screen.findByText(/your dataset/i)).toBeInTheDocument();
  });

  it("a changed portion rewrites the meal (meal_id) and is named in the confirmed text", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealId={5} mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));
    fireEvent.click(await screen.findByRole("button", { name: /adjust a portion/i }));
    fireEvent.change(screen.getByLabelText(/grams of oats/i), {
      target: { value: "100" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save as confirmed/i }));
    // meal_id is sent so the backend rewrites the logged entry to the new portion…
    await waitFor(() =>
      expect(api.confirmMeal).toHaveBeenCalledWith(
        "oatmeal",
        expect.anything(),
        expect.anything(),
        5,
      ),
    );
    // …and the confirmed message names the change.
    expect(await screen.findByText(/updated oats to 100 g/i)).toBeInTheDocument();
  });

  it("locks once confirmed — no undo or change affordance remains", async () => {
    vi.mocked(api.confirmMeal).mockResolvedValue({ ok: true, id: 1, confirmations: 6 });
    render(<MealReview mealText="oatmeal" perItem={perItem} totals={totals} />);

    fireEvent.click(screen.getByRole("button", { name: /looks right/i }));
    fireEvent.click(await screen.findByRole("button", { name: /confirm it/i }));
    await screen.findByText(/your dataset/i);
    // Terminal state: no buttons to nudge, undo, or re-open the correction box.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
