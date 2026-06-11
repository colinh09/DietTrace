import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SafetyNotice } from "@/components/safety-notice";

// The calm guardrail notice surfaced when a logged input trips the safety check.
// It shows the supportive message; an all-clear render is empty.
describe("SafetyNotice", () => {
  it("shows the supportive message when the input is flagged", () => {
    render(
      <SafetyNotice
        safety={{
          flagged: true,
          category: "disordered_eating",
          message: "You deserve support — you're not alone.",
        }}
      />,
    );
    expect(screen.getByRole("note")).toHaveTextContent(
      /you deserve support/i,
    );
  });

  it("renders nothing for a normal, unflagged log", () => {
    const { container } = render(
      <SafetyNotice safety={{ flagged: false, category: null, message: "" }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when there is no safety result yet", () => {
    const { container } = render(<SafetyNotice safety={undefined} />);
    expect(container).toBeEmptyDOMElement();
  });
});
