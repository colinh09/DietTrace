import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  HOW_STEPS,
  HowItWorksGuide,
  Tour,
  TourPrompt,
} from "@/components/how-it-works";

describe("HowItWorksGuide", () => {
  it("explains every part of the app and offers the tour", () => {
    const onStartTour = vi.fn();
    render(<HowItWorksGuide onStartTour={onStartTour} />);

    // The written guide covers each part of the app, in plain language.
    for (const step of HOW_STEPS) {
      expect(screen.getByText(step.title)).toBeInTheDocument();
    }

    fireEvent.click(screen.getByRole("button", { name: /take the tour/i }));
    expect(onStartTour).toHaveBeenCalledTimes(1);
  });

  it("omits the tour button when no handler is given (the tab alone)", () => {
    render(<HowItWorksGuide />);
    expect(
      screen.queryByRole("button", { name: /take the tour/i }),
    ).not.toBeInTheDocument();
  });
});

describe("Tour", () => {
  it("steps forward and back through each part, then finishes", () => {
    const onClose = vi.fn();
    render(<Tour onClose={onClose} />);

    expect(screen.getByText(HOW_STEPS[0].title)).toBeInTheDocument();
    expect(screen.getByText(`1 / ${HOW_STEPS.length}`)).toBeInTheDocument();
    // No "Back" on the first step.
    expect(screen.queryByRole("button", { name: /^back$/i })).toBeNull();

    for (let i = 1; i < HOW_STEPS.length; i++) {
      fireEvent.click(screen.getByRole("button", { name: /next/i }));
      expect(screen.getByText(HOW_STEPS[i].title)).toBeInTheDocument();
    }

    // The last step finishes instead of advancing.
    expect(screen.queryByRole("button", { name: /next/i })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /back/i }));
    expect(
      screen.getByText(HOW_STEPS[HOW_STEPS.length - 2].title),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /next/i }));
    fireEvent.click(screen.getByRole("button", { name: /done/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("is dismissible at any point via the close control", () => {
    const onClose = vi.fn();
    render(<Tour onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("TourPrompt", () => {
  beforeEach(() => window.localStorage.clear());

  it("proactively offers the tour and launches it", () => {
    const onStartTour = vi.fn();
    render(<TourPrompt onStartTour={onStartTour} />);
    fireEvent.click(screen.getByRole("button", { name: /take the tour/i }));
    expect(onStartTour).toHaveBeenCalledTimes(1);
  });

  it("is dismissible and stays dismissed on the next visit", () => {
    const { unmount } = render(<TourPrompt onStartTour={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
    expect(
      screen.queryByRole("button", { name: /take the tour/i }),
    ).not.toBeInTheDocument();

    unmount();
    render(<TourPrompt onStartTour={vi.fn()} />);
    expect(
      screen.queryByRole("button", { name: /take the tour/i }),
    ).not.toBeInTheDocument();
  });
});
