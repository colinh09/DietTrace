import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Sparkline } from "@/components/sparkline";

describe("Sparkline", () => {
  it("renders an accessible graphic for a series of daily totals", () => {
    const { container } = render(
      <Sparkline data={[1800, 1950, 2100, 1700, 2000, 1850, 1000]} target={2000} />,
    );
    expect(screen.getByRole("img", { name: /7-day/i })).toBeInTheDocument();
    // The line + area paths are drawn (no NaN coordinates).
    const paths = container.querySelectorAll("path");
    expect(paths.length).toBeGreaterThan(0);
    paths.forEach((p) => expect(p.getAttribute("d")).not.toMatch(/NaN/));
  });

  it("renders nothing for an empty series instead of a broken chart", () => {
    const { container } = render(<Sparkline data={[]} />);
    expect(container.firstChild).toBeNull();
  });
});
