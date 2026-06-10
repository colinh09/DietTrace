import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SeededModal } from "@/components/seeded-modal";
import type { SeedDemoResult } from "@/lib/api";

const result: SeedDemoResult = {
  seeded: true,
  meals: 4,
  meal_date: "2026-06-06",
  dataset_date: "2026-06-05",
  goals_set: true,
  confirmations: 5,
  corrections: 2,
  persona: {
    key: "runner",
    label: "Endurance runner",
    blurb: "Under-logs her training carbs.",
    goal_rationale: "Sample targets for a marathon runner.",
    hook_meal: "spaghetti",
    hook_note: "The spaghetti logged at ~196 kcal — far low.",
    learns: "Her preworkout carbs run high.",
    meal_texts: [
      "oatmeal before my run",
      "a big plate of spaghetti the night before",
    ],
    confirmation_texts: ["oatmeal before the gym"],
    correction_texts: [
      "before workouts I eat way more carbs",
      "my preworkout oats are bigger",
    ],
  },
};

describe("SeededModal", () => {
  it("explains the loaded persona, the seeded state, and flags the under-count", () => {
    render(
      <SeededModal
        result={result}
        busy={false}
        onReseed={() => {}}
        onClose={() => {}}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Endurance runner" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/big plate of spaghetti/i)).toBeInTheDocument();
    // The hook meal carries the "under-counted" amber chip.
    expect(document.querySelector(".dm-meal .chip.amber")).toHaveTextContent(
      /under-counted/i,
    );
    // "Your Dataset" framing is kept in the what's-loaded stats.
    expect(screen.getByText(/in Your Dataset/i)).toBeInTheDocument();
  });

  it("re-seeds the other persona via the loader", () => {
    const onReseed = vi.fn();
    render(
      <SeededModal
        result={result}
        busy={false}
        onReseed={onReseed}
        onClose={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Bodybuilder/i }));
    expect(onReseed).toHaveBeenCalledWith("bodybuilder");
  });

  it("jumps to the dataset day and closes", () => {
    const onViewDataset = vi.fn();
    const onClose = vi.fn();
    render(
      <SeededModal
        result={result}
        busy={false}
        onReseed={() => {}}
        onViewDataset={onViewDataset}
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /see the confirmed meals/i }));
    expect(onViewDataset).toHaveBeenCalledWith("2026-06-05");
    expect(onClose).toHaveBeenCalled();
  });
});
