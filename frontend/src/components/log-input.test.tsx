import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LogInput } from "@/components/log-input";
import { logMeal, type LogResponse } from "@/lib/api";

// The component owns the API call; mock it so the test stays offline.
vi.mock("@/lib/api", () => ({ logMeal: vi.fn() }));

const result: LogResponse = {
  id: 7,
  per_item: [
    { fdc_id: 123, description: "Egg, whole, cooked", grams: 100, nutrients: [] },
  ],
  totals: [{ code: "208", name: "Energy", amount: 540, unit: "kcal" }],
  trace: [],
};

describe("LogInput", () => {
  beforeEach(() => {
    vi.mocked(logMeal).mockReset();
  });

  it("renders the italic 'what did you eat?' input and a Log control", () => {
    render(<LogInput onLogged={() => {}} />);
    expect(screen.getByPlaceholderText("what did you eat?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^log$/i })).toBeInTheDocument();
  });

  it("logs the meal on Enter and drops the trimmed result via onLogged", async () => {
    vi.mocked(logMeal).mockResolvedValue(result);
    const onLogged = vi.fn();
    render(<LogInput onLogged={onLogged} />);
    const input = screen.getByPlaceholderText("what did you eat?") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "  2 eggs  " } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    await waitFor(() => expect(onLogged).toHaveBeenCalledTimes(1));
    expect(logMeal).toHaveBeenCalledWith("2 eggs");
    expect(onLogged).toHaveBeenCalledWith("2 eggs", result);
    // The input clears after a successful log, ready for the next meal.
    expect(input.value).toBe("");
  });

  it("logs the meal when the Log button is clicked", async () => {
    vi.mocked(logMeal).mockResolvedValue(result);
    const onLogged = vi.fn();
    render(<LogInput onLogged={onLogged} />);
    fireEvent.change(screen.getByPlaceholderText("what did you eat?"), {
      target: { value: "oatmeal" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^log$/i }));

    await waitFor(() => expect(logMeal).toHaveBeenCalledWith("oatmeal"));
    expect(onLogged).toHaveBeenCalledWith("oatmeal", result);
  });

  it("ignores an empty (or whitespace-only) submission", () => {
    const onLogged = vi.fn();
    render(<LogInput onLogged={onLogged} />);
    fireEvent.change(screen.getByPlaceholderText("what did you eat?"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("button", { name: /^log$/i }));
    expect(logMeal).not.toHaveBeenCalled();
    expect(onLogged).not.toHaveBeenCalled();
  });

  it("moves empty → processing → result across the log lifecycle", async () => {
    let resolveLog!: (r: LogResponse) => void;
    vi.mocked(logMeal).mockReturnValue(
      new Promise<LogResponse>((r) => {
        resolveLog = r;
      }),
    );
    render(<LogInput onLogged={() => {}} />);
    fireEvent.change(screen.getByPlaceholderText("what did you eat?"), {
      target: { value: "banana" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^log$/i }));

    // processing: the control reflects the in-flight log.
    expect(screen.getByRole("button", { name: /logging/i })).toBeInTheDocument();

    resolveLog(result);

    // result: a brief confirmation once the meal lands in the list.
    await screen.findByText(/logged/i);
  });

  it("recovers to empty when the log fails", async () => {
    vi.mocked(logMeal).mockRejectedValue(new Error("boom"));
    const onLogged = vi.fn();
    render(<LogInput onLogged={onLogged} />);
    const input = screen.getByPlaceholderText("what did you eat?") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "steak" } });
    fireEvent.click(screen.getByRole("button", { name: /^log$/i }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^log$/i })).toBeInTheDocument(),
    );
    expect(onLogged).not.toHaveBeenCalled();
    // The text is kept so the meal can be retried.
    expect(input.value).toBe("steak");
  });
});
