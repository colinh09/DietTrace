import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DemoSeedButton } from "@/components/demo-seed-button";
import { seedDemo } from "@/lib/api";

vi.mock("@/lib/api", () => ({ seedDemo: vi.fn() }));

const okResult = { seeded: true, meals: 4, goals_set: true };

describe("DemoSeedButton", () => {
  it("renders 'See it in action' and calls seedDemo on click", async () => {
    vi.mocked(seedDemo).mockResolvedValue(okResult);
    const onSeeded = vi.fn();
    render(<DemoSeedButton onSeeded={onSeeded} />);

    const btn = screen.getByRole("button", { name: /see it in action/i });
    expect(btn).toBeInTheDocument();

    fireEvent.click(btn);

    await waitFor(() => expect(onSeeded).toHaveBeenCalledTimes(1));
    expect(seedDemo).toHaveBeenCalledTimes(1);
  });

  it("disables the button while seeding is in flight", async () => {
    let resolve!: (v: typeof okResult) => void;
    const pending = new Promise<typeof okResult>((r) => {
      resolve = r;
    });
    vi.mocked(seedDemo).mockReturnValue(pending);

    render(<DemoSeedButton onSeeded={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /see it in action/i }));

    await waitFor(() =>
      expect(screen.getByRole("button")).toBeDisabled(),
    );

    resolve(okResult);
    await waitFor(() =>
      expect(screen.getByRole("button")).not.toBeDisabled(),
    );
  });

  it("still re-enables after an API error", async () => {
    vi.mocked(seedDemo).mockRejectedValue(new Error("network error"));

    render(<DemoSeedButton onSeeded={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /see it in action/i }));

    await waitFor(() =>
      expect(screen.getByRole("button")).not.toBeDisabled(),
    );
  });
});
