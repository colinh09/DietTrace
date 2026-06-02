import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LogInput } from "@/components/log-input";

// The page owns the API call now; LogInput only hands up the trimmed text.
describe("LogInput", () => {
  it("submits the trimmed text and clears the field", () => {
    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={false} />);
    const field = screen.getByRole("textbox", {
      name: /what did you eat/i,
    }) as HTMLInputElement;

    fireEvent.change(field, { target: { value: "  two eggs  " } });
    fireEvent.click(screen.getByRole("button", { name: /^log$/i }));

    expect(onSubmit).toHaveBeenCalledWith("two eggs");
    expect(field.value).toBe("");
  });

  it("does not submit when empty", () => {
    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={false} />);
    fireEvent.click(screen.getByRole("button", { name: /^log$/i }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("disables and shows a busy label while a stream is in flight", () => {
    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={true} />);
    const field = screen.getByRole("textbox", {
      name: /what did you eat/i,
    }) as HTMLInputElement;

    expect(field.disabled).toBe(true);
    expect(screen.getByRole("button", { name: /logging/i })).toBeInTheDocument();
  });
});

// Voice logging: a mic button drives the browser Web Speech
// API, transcribing speech into the input so the existing submit can send it.
// Must fail soft (no mic button at all) when the browser lacks the API.
describe("LogInput voice", () => {
  // A minimal SpeechRecognition stand-in we can drive from the test.
  class MockRecognition {
    lang = "";
    interimResults = false;
    onresult: ((e: unknown) => void) | null = null;
    onerror: ((e: unknown) => void) | null = null;
    onend: (() => void) | null = null;
    start = vi.fn();
    stop = vi.fn();
    // Helper for the test to deliver a transcript like the real API would.
    emit(transcript: string) {
      this.onresult?.({ results: [[{ transcript }]] });
    }
  }

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).SpeechRecognition;
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  });

  it("transcribes speech into the field when supported", () => {
    let instance: MockRecognition | null = null;
    (window as unknown as Record<string, unknown>).SpeechRecognition =
      function () {
        instance = new MockRecognition();
        return instance;
      };

    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={false} />);

    const mic = screen.getByRole("button", { name: /voice/i });
    fireEvent.click(mic);
    expect(instance).not.toBeNull();
    expect(instance!.start).toHaveBeenCalled();

    act(() => instance!.emit("grilled salmon and rice"));

    const field = screen.getByRole("textbox", {
      name: /what did you eat/i,
    }) as HTMLInputElement;
    expect(field.value).toBe("grilled salmon and rice");
  });

  it("fails soft with no mic button when the API is unavailable", () => {
    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={false} />);
    expect(
      screen.queryByRole("button", { name: /voice/i }),
    ).not.toBeInTheDocument();
  });

  it("does not show the mic while a stream is in flight", () => {
    (window as unknown as Record<string, unknown>).SpeechRecognition =
      function () {
        return new MockRecognition();
      };
    const onSubmit = vi.fn();
    render(<LogInput onSubmit={onSubmit} busy={true} />);
    expect(
      screen.queryByRole("button", { name: /voice/i }),
    ).not.toBeInTheDocument();
  });
});
