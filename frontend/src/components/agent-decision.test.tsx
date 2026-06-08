import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AgentDecision, AgentFeed } from "@/components/agent-decision";

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
    expect(line).toHaveTextContent(/your dataset/i);
    expect(line).toHaveTextContent(/clean meal accepted/i);
    expect(line).toHaveAttribute("data-op", "add_dataset_point");
  });

  it("labels a retune decision", () => {
    render(
      <AgentDecision decision={{ op: "retune", reason: "enough new signal" }} />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/updated/i);
  });

  it("renders nothing when no decision is present", () => {
    const { container } = render(<AgentDecision />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("AgentFeed", () => {
  it("lists each decision with its meal and reason", () => {
    render(
      <AgentFeed
        events={[
          { id: 2, op: "retune", reason: "enough new signal", mealText: "an apple" },
          { id: 1, op: "add_dataset_point", reason: "clean meal", mealText: "two eggs" },
        ]}
      />,
    );
    const feed = screen.getByLabelText("Agent activity");
    expect(feed.querySelectorAll(".revent")).toHaveLength(2);
    expect(screen.getByText("an apple")).toBeInTheDocument();
    expect(screen.getByText(/updated/i)).toBeInTheDocument();
    expect(screen.getByText("two eggs")).toBeInTheDocument();
  });

  it("renders nothing when there are no events", () => {
    const { container } = render(<AgentFeed events={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
