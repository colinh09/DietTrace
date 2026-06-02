import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TaughtPanel } from "@/components/taught-panel";

// The "what you've taught" panel lists the user's portion corrections as
// food · before → after grams. Empty input renders nothing.
describe("TaughtPanel", () => {
  it("lists each correction as before → after grams", () => {
    render(
      <TaughtPanel
        corrections={[
          {
            food: "oatmeal",
            original_grams: 80,
            corrected_grams: 120,
            created_at: "2026-06-01T12:00:00Z",
          },
        ]}
      />,
    );
    expect(screen.getByText("oatmeal")).toBeInTheDocument();
    expect(screen.getByText(/80 g/)).toHaveTextContent(/80 g\s*→\s*120 g/);
  });

  it("renders nothing when there are no corrections", () => {
    const { container } = render(<TaughtPanel corrections={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
