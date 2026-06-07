import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentDecision } from "@/components/agent-decision";

// The agent-observability line surfacing the supervisor's per-meal decision.
describe("AgentDecision", () => {
  it("renders the chosen op label and its reason", () => {
    render(
      <AgentDecision
        decision={{
          op: "add_dataset_point",
          reason: "clean meal accepted as-is",
        }}
      />,
    );
    const line = screen.getByRole("status");
    expect(line).toHaveTextContent(/held-out dataset/i);
    expect(line).toHaveTextContent(/clean meal accepted/i);
    expect(line).toHaveAttribute("data-op", "add_dataset_point");
  });

  it("labels a retune decision", () => {
    render(
      <AgentDecision decision={{ op: "retune", reason: "enough new signal" }} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/retuning/i);
  });

  it("renders nothing when no decision is present", () => {
    const { container } = render(<AgentDecision />);
    expect(container).toBeEmptyDOMElement();
  });
});
