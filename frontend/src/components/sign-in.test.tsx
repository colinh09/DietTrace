import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SignIn } from "@/components/sign-in";
import { useAuth } from "@/lib/auth";

vi.mock("@/lib/auth", () => ({ useAuth: vi.fn() }));

const base = {
  user: null,
  loading: false,
  configured: true,
  signInWithGoogle: vi.fn(),
  signOut: vi.fn(),
};

describe("SignIn", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the sign-in screen with both entry paths", () => {
    vi.mocked(useAuth).mockReturnValue({ ...base });
    render(<SignIn onContinueAnon={vi.fn()} />);
    expect(screen.getByText("DietTrace")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /continue with google/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /without an account/i }),
    ).toBeInTheDocument();
  });

  it("calls signInWithGoogle when Continue with Google is clicked", async () => {
    const signInWithGoogle = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({ ...base, signInWithGoogle });
    render(<SignIn onContinueAnon={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /continue with google/i }));
    await waitFor(() => expect(signInWithGoogle).toHaveBeenCalledTimes(1));
  });

  it("calls onContinueAnon for the anonymous path", () => {
    vi.mocked(useAuth).mockReturnValue({ ...base });
    const onContinueAnon = vi.fn();
    render(<SignIn onContinueAnon={onContinueAnon} />);

    fireEvent.click(screen.getByRole("button", { name: /without an account/i }));
    expect(onContinueAnon).toHaveBeenCalledTimes(1);
  });

  it("stays graceful when Firebase is unconfigured — no Google button, anon path works", () => {
    vi.mocked(useAuth).mockReturnValue({ ...base, configured: false });
    const onContinueAnon = vi.fn();
    render(<SignIn onContinueAnon={onContinueAnon} />);

    expect(
      screen.queryByRole("button", { name: /continue with google/i }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /without an account/i }));
    expect(onContinueAnon).toHaveBeenCalledTimes(1);
  });
});
