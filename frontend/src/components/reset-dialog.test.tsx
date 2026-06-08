import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResetDialog } from "@/components/reset-dialog";
import { resetSession } from "@/lib/api";

vi.mock("@/lib/api", () => ({ resetSession: vi.fn() }));

const okResult = { reset: true, cleared: { meals: 4, goals: 1 } };

describe("ResetDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a real confirmation dialog with Cancel and Reset", () => {
    render(<ResetDialog onClose={() => {}} onReset={() => {}} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/reset everything\?/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^cancel$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^reset$/i })).toBeInTheDocument();
  });

  it("cancels without resetting", () => {
    const onClose = vi.fn();
    render(<ResetDialog onClose={onClose} onReset={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(resetSession).not.toHaveBeenCalled();
  });

  it("commits the reset, then fires onReset and closes", async () => {
    vi.mocked(resetSession).mockResolvedValue(okResult);
    const onClose = vi.fn();
    const onReset = vi.fn();
    render(<ResetDialog onClose={onClose} onReset={onReset} />);

    fireEvent.click(screen.getByRole("button", { name: /^reset$/i }));
    await waitFor(() => expect(onReset).toHaveBeenCalledTimes(1));
    expect(resetSession).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalled();
  });

  it("still recovers (onReset fires) after an API error", async () => {
    vi.mocked(resetSession).mockRejectedValue(new Error("network error"));
    const onReset = vi.fn();
    render(<ResetDialog onClose={() => {}} onReset={onReset} />);
    fireEvent.click(screen.getByRole("button", { name: /^reset$/i }));
    await waitFor(() => expect(onReset).toHaveBeenCalledTimes(1));
  });
});
