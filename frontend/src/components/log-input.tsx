"use client";

// The inline log input: a calm "what did you eat?" field. On Enter or the Log
// button it hands the text up via `onSubmit`; the page streams it to /log/stream
// and shows the agent's work live. `busy` is driven by the page while a
// stream is in flight, disabling the field until the meal settles.
import { useState } from "react";

export function LogInput({
  onSubmit,
  busy,
}: {
  onSubmit: (text: string) => void;
  busy: boolean;
}) {
  const [text, setText] = useState("");

  function submit() {
    const meal = text.trim();
    if (!meal || busy) return;
    setText("");
    onSubmit(meal);
  }

  return (
    <form
      className={"loginput" + (busy ? " on" : "")}
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <input
        className="loginput-field"
        value={text}
        placeholder="what did you eat?"
        disabled={busy}
        aria-label="what did you eat?"
        onChange={(e) => setText(e.target.value)}
      />
      <button type="submit" className="loginput-btn" disabled={busy}>
        {busy ? "Logging…" : "Log"}
      </button>
    </form>
  );
}
