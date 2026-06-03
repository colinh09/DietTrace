import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LogInput } from "@/components/log-input";

// The page owns the API call now; LogInput only hands up the trimmed text.
describe("LogInput", () => {
  it("submits the trimmed text and clears the field", () => {
    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={false} />);
    const field = screen.getByRole("textbox", {
      name: /what did you eat/i,
    }) as HTMLInputElement;

    fireEvent.change(field, { target: { value: "  two eggs  " } });
    fireEvent.click(screen.getByRole("button", { name: /^log$/i }));

    expect(onSubmit).toHaveBeenCalledWith("two eggs");
    expect(field.value).toBe("");
  });

  it("does not submit when empty", () => {
    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={false} />);
    fireEvent.click(screen.getByRole("button", { name: /^log$/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables and shows a busy label while a stream is in flight", () => {
    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={true} />);
    const field = screen.getByRole("textbox", {
      name: /what did you eat/i,
    }) as HTMLInputElement;

    expect(field.disabled).toBe(true);
    expect(screen.getByRole("button", { name: /logging/i })).toBeInTheDocument();
  });
});
