import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Header } from "@/components/header";

const may30 = new Date(2026, 4, 30);

describe("Header", () => {
  it("renders the DietTrace brand and the formatted date", () => {
    render(<Header date={may30} onShift={() => {}} onPickDate={() => {}} />);
    expect(screen.getByText("DietTrace")).toBeInTheDocument();
    expect(screen.getByText("Sat, May 30")).toBeInTheDocument();
  });

  it("shifts the day back and forward via the date arrows", () => {
    const onShift = vi.fn();
    render(<Header date={may30} onShift={onShift} onPickDate={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /previous day/i }));
    fireEvent.click(screen.getByRole("button", { name: /next day/i }));
    expect(onShift).toHaveBeenNthCalledWith(1, -1);
    expect(onShift).toHaveBeenNthCalledWith(2, 1);
  });

  it("opens the calendar affordance and picks a day", () => {
    const onPickDate = vi.fn();
    render(<Header date={may30} onShift={() => {}} onPickDate={onPickDate} />);
    // The calendar is closed until the affordance is clicked.
    expect(screen.queryByRole("grid")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /open calendar/i }));
    expect(screen.getByRole("grid")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "15" }));
    expect(onPickDate).toHaveBeenCalledTimes(1);
    const picked = onPickDate.mock.calls[0][0] as Date;
    expect(picked.getFullYear()).toBe(2026);
    expect(picked.getMonth()).toBe(4);
    expect(picked.getDate()).toBe(15);
  });
});
