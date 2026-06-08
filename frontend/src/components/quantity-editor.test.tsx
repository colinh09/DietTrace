import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QuantityEditor } from "@/components/quantity-editor";

vi.mock("@/lib/api", () => ({ confirmMeal: vi.fn() }));

const perItem = [{ fdc_id: 1, description: "oats", grams: 80, nutrients: [] }];

describe("QuantityEditor", () => {
  it("strips a stuck leading zero from the grams input", () => {
    render(
      <QuantityEditor
        mealText="oatmeal"
        perItem={perItem}
        onConfirmed={() => {}}
        onCancel={() => {}}
      />,
    );
    const input = screen.getByLabelText(/grams of oats/i) as HTMLInputElement;
    expect(input.value).toBe("80");
    // The classic stale-number-input bug: "011" must normalise to "11"…
    fireEvent.change(input, { target: { value: "011" } });
    expect(input.value).toBe("11");
    // …but a lone "0" (and an empty field while editing) is preserved.
    fireEvent.change(input, { target: { value: "0" } });
    expect(input.value).toBe("0");
    fireEvent.change(input, { target: { value: "" } });
    expect(input.value).toBe("");
  });
});
