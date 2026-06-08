import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { AccountMenu } from "@/components/account-menu";
import { useAuth } from "@/lib/auth";

// resetSession is only reached after a confirm click; stub it so the dialog is inert.
import { vi } from "vitest";
vi.mock("@/lib/api", () => ({ resetSession: vi.fn().mockResolvedValue({ reset: true }) }));

// Auth is mocked; anonymous (unconfigured) is the default so the existing
// persona-label behavior is unchanged. Individual tests override per case.
vi.mock("@/lib/auth", () => ({ useAuth: vi.fn() }));
const anonAuth = {
  user: null,
  loading: false,
  configured: false,
  signInWithGoogle: vi.fn(),
  signOut: vi.fn(),
};
beforeEach(() => {
  vi.mocked(useAuth).mockReturnValue({ ...anonAuth });
});

describe("AccountMenu", () => {
  it("hides the account actions behind the avatar until it's opened", () => {
    render(<AccountMenu />);
    expect(screen.getByRole("button", { name: /account/i })).toBeInTheDocument();
    // Persona details + Reset are folded into the menu — not in the chrome.
    expect(screen.queryByText(/persona details/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/reset everything/i)).not.toBeInTheDocument();
  });

  it("opens the menu with Persona details and a Reset action", () => {
    render(<AccountMenu />);
    fireEvent.click(screen.getByRole("button", { name: /account/i }));
    expect(screen.getByText(/persona details/i)).toBeInTheDocument();
    expect(screen.getByText(/reset everything/i)).toBeInTheDocument();
  });

  it("opens the persona-details surface from the menu", () => {
    render(<AccountMenu />);
    fireEvent.click(screen.getByRole("button", { name: /account/i }));
    fireEvent.click(screen.getByText(/persona details/i));
    // With no saved setup (empty localStorage) the calm empty state shows.
    expect(screen.getByText(/nothing set up yet/i)).toBeInTheDocument();
  });

  it("opens the Reset confirmation modal from the menu (no in-place morph)", () => {
    render(<AccountMenu />);
    fireEvent.click(screen.getByRole("button", { name: /account/i }));
    fireEvent.click(screen.getByText(/reset everything/i));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(/reset everything\?/i)).toBeInTheDocument();
  });

  it("shows the signed-in user and a Sign out action when authenticated", async () => {
    const signOut = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      ...anonAuth,
      configured: true,
      user: { displayName: "Colin Hwang", email: "c@x.com", photoURL: null } as never,
      signOut,
    });
    render(<AccountMenu />);
    fireEvent.click(screen.getByRole("button", { name: /account/i }));
    expect(screen.getByText("Colin Hwang")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: /sign out/i }));
    await waitFor(() => expect(signOut).toHaveBeenCalledTimes(1));
  });

  it("offers Sign in when configured but signed out (anonymous session)", async () => {
    const signInWithGoogle = vi.fn().mockResolvedValue(undefined);
    vi.mocked(useAuth).mockReturnValue({
      ...anonAuth,
      configured: true,
      signInWithGoogle,
    });
    render(<AccountMenu />);
    fireEvent.click(screen.getByRole("button", { name: /account/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /sign in/i }));
    await waitFor(() => expect(signInWithGoogle).toHaveBeenCalledTimes(1));
  });
});
