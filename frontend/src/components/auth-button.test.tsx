import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthButton } from "@/components/auth-button";
import { useAuth } from "@/lib/auth";

vi.mock("@/lib/auth", () => ({ useAuth: vi.fn() }));

const base = {
  user: null,
  loading: false,
  configured: true,
  signInWithGoogle: vi.fn(),
  signOut: vi.fn(),
};

describe("AuthButton", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders nothing when Firebase isn't configured", () => {
    vi.mocked(useAuth).mockReturnValue({ ...base, configured: false });
    const { container } = render(<AuthButton />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing while auth is still loading", () => {
    vi.mocked(useAuth).mockReturnValue({ ...base, loading: true });
    const { container } = render(<AuthButton />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a Sign in button when signed out and calls signInWithGoogle", async () => {
    const signInWithGoogle = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({ ...base, signInWithGoogle });
    const onAuthChange = vi.fn();
    render(<AuthButton onAuthChange={onAuthChange} />);

    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(signInWithGoogle).toHaveBeenCalledTimes(1));
    expect(onAuthChange).toHaveBeenCalledTimes(1);
  });

  it("shows the user's name and a sign-out control when signed in", async () => {
    const signOut = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      ...base,
      user: { displayName: "Colin Hwang", email: "c@x.com", photoURL: null } as never,
      signOut,
    });
    render(<AuthButton />);

    expect(screen.getByText("Colin")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));
    await waitFor(() => expect(signOut).toHaveBeenCalledTimes(1));
  });
});
