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

  it("shows an Accuracy recap (both sets) and a full-sentence headline on a shipped retune", () => {
    render(
      <AgentFeed
        events={[
          {
            id: 9,
            op: "retune",
            reason: "Pre-run meals run carb-heavy",
            recap: {
              shipped: true,
              fitBefore: 0.61,
              fitAfter: 0.86,
              usdaBefore: 1,
              usdaAfter: 1,
            },
          },
        ]}
      />,
    );
    expect(screen.getByText("Your dataset has been updated")).toBeInTheDocument();
    expect(screen.getByText("Agent recap")).toBeInTheDocument();
    expect(screen.getByText("Accuracy recap")).toBeInTheDocument();
    expect(screen.getByText("Your dataset")).toBeInTheDocument();
    expect(screen.getByText("USDA")).toBeInTheDocument();
    expect(screen.getByText("61%")).toBeInTheDocument();
    expect(screen.getByText("86%")).toBeInTheDocument();
    expect(
      screen.getByText(/more accurately estimated calories/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/didn't drop below the floor/i)).toBeInTheDocument();
  });

  it("headlines a rejected retune as 'no update'", () => {
    render(
      <AgentFeed
        events={[
          {
            id: 10,
            op: "retune",
            reason: "no change — it wasn't more accurate",
            recap: {
              shipped: false,
              fitBefore: 0.7,
              fitAfter: 0.7,
              usdaBefore: 1,
              usdaAfter: 1,
            },
          },
        ]}
      />,
    );
    expect(
      screen.getByText(/no update — accuracy didn't improve/i),
    ).toBeInTheDocument();
  });

  it("renders nothing when there are no events", () => {
    const { container } = render(<AgentFeed events={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
