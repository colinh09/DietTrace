import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Header } from "@/components/header";

// The account menu's Reset path stubs the API; it's never reached here.
vi.mock("@/lib/api", () => ({ resetSession: vi.fn().mockResolvedValue({ reset: true }) }));

const may30 = new Date(2026, 4, 30);

describe("Header", () => {
  it("renders the brand and the right-aligned primary tabs (no date picker)", () => {
    render(<Header date={may30} />);
    expect(screen.getByText("DietTrace")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Today" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Macros" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "How it works" })).toBeInTheDocument();
    // The date navigation lives in the day card now, not the navbar.
    expect(screen.queryByRole("button", { name: /open calendar/i })).not.toBeInTheDocument();
  });

  it("folds Persona details + Reset into the account menu, not the tabs", () => {
    render(<Header date={may30} />);
    // Constant chrome: the destructive + modal-opener actions aren't tabs.
    expect(screen.queryByText(/your details/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/reset everything/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /account/i }));
    expect(screen.getByText(/your details/i)).toBeInTheDocument();
    expect(screen.getByText(/reset everything/i)).toBeInTheDocument();
  });

  it("opens the Overview and the Macros editor from the navbar", () => {
    const onOpenOverview = vi.fn();
    const onOpenMacros = vi.fn();
    render(
      <Header date={may30} onOpenOverview={onOpenOverview} onOpenMacros={onOpenMacros} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "How it works" }));
    fireEvent.click(screen.getByRole("button", { name: "Macros" }));
    expect(onOpenOverview).toHaveBeenCalledTimes(1);
    expect(onOpenMacros).toHaveBeenCalledTimes(1);
  });
});
