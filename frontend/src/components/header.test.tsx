import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Header } from "@/components/header";

const may30 = new Date(2026, 4, 30);

describe("Header", () => {
  it("renders the brand and the evenly-spaced nav tabs (no date picker)", () => {
    render(<Header date={may30} />);
    expect(screen.getByText("DietTrace")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Today" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Macros" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Overview" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /persona details/i })).toBeInTheDocument();
    // The date navigation lives in the day card now, not the navbar.
    expect(screen.queryByRole("button", { name: /open calendar/i })).not.toBeInTheDocument();
  });

  it("opens the Overview and the Macros editor from the navbar", () => {
    const onOpenOverview = vi.fn();
    const onOpenMacros = vi.fn();
    render(
      <Header date={may30} onOpenOverview={onOpenOverview} onOpenMacros={onOpenMacros} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    fireEvent.click(screen.getByRole("button", { name: "Macros" }));
    expect(onOpenOverview).toHaveBeenCalledTimes(1);
    expect(onOpenMacros).toHaveBeenCalledTimes(1);
  });
});
