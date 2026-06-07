import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResetSessionButton } from "@/components/reset-session-button";
import { resetSession } from "@/lib/api";

vi.mock("@/lib/api", () => ({ resetSession: vi.fn() }));

const okResult = { reset: true, cleared: { meals: 4, goals: 1 } };

describe("ResetSessionButton", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requires a confirm click before resetting", async () => {
    vi.mocked(resetSession).mockResolvedValue(okResult);
    const onReset = vi.fn();
    render(<ResetSessionButton onReset={onReset} />);

    // First click only arms the confirm — no API call yet.
    fireEvent.click(screen.getByRole("button", { name: /^reset$/i }));
    expect(resetSession).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /reset everything/i })).toBeInTheDocument();

    // Second click commits.
    fireEvent.click(screen.getByRole("button", { name: /reset everything/i }));
    await waitFor(() => expect(onReset).toHaveBeenCalledTimes(1));
    expect(resetSession).toHaveBeenCalledTimes(1);
  });

  it("cancels the confirm on blur without resetting", () => {
    vi.mocked(resetSession).mockResolvedValue(okResult);
    render(<ResetSessionButton onReset={() => {}} />);

    const btn = screen.getByRole("button", { name: /^reset$/i });
    fireEvent.click(btn);
    fireEvent.blur(screen.getByRole("button", { name: /reset everything/i }));

    expect(screen.getByRole("button", { name: /^reset$/i })).toBeInTheDocument();
    expect(resetSession).not.toHaveBeenCalled();
  });

  it("still re-enables after an API error", async () => {
    vi.mocked(resetSession).mockRejectedValue(new Error("network error"));
    render(<ResetSessionButton onReset={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /^reset$/i }));
    fireEvent.click(screen.getByRole("button", { name: /reset everything/i }));

    await waitFor(() => expect(screen.getByRole("button")).not.toBeDisabled());
  });
});
