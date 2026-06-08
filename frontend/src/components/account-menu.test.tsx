import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AccountMenu } from "@/components/account-menu";

// resetSession is only reached after a confirm click; stub it so the dialog is inert.
import { vi } from "vitest";
vi.mock("@/lib/api", () => ({ resetSession: vi.fn().mockResolvedValue({ reset: true }) }));

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
});
