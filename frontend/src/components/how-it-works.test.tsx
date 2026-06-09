import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HowItWorksGuide } from "@/components/how-it-works";

describe("HowItWorksGuide", () => {
  it("renders the written how-it-works section with each part of the app", () => {
    render(<HowItWorksGuide />);
    expect(
      screen.getByRole("heading", { name: /how diettrace works/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/your day at a glance/i)).toBeInTheDocument();
    expect(screen.getByText(/log food in plain english/i)).toBeInTheDocument();
    expect(screen.getByText(/proves it stays accurate/i)).toBeInTheDocument();
    // We standardized on "dataset", never "answer key".
    expect(screen.queryByText(/answer key/i)).not.toBeInTheDocument();
  });
});
