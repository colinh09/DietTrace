"use client";

// The inline log input: an italic "what did you eat?" field that POSTs the
// natural-language meal to /log on Enter or the Log button, then runs a calm
// empty → processing → result transition while the agent works. On success it
// clears itself and hands the logged meal up via `onLogged` so it drops into
// today's list. The meal list itself lands in 9.6.
import { useState } from "react";
import { logMeal, type LogResponse } from "@/lib/api";

// empty: idle, ready for input. processing: a /log call is in flight.
// result: a brief confirmation right after the meal lands in the list.
type Status = "empty" | "processing" | "result";

export function LogInput({
  onLogged,
  date,
}: {
  onLogged: (text: string, result: LogResponse) => void;
  // The viewed calendar day (YYYY-MM-DD) the meal is filed under.
  date?: string;
}) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<Status>("empty");

  async function submit() {
    const meal = text.trim();
    if (!meal || status === "processing") return;
    setStatus("processing");
    try {
      const result = await logMeal(meal, date);
      onLogged(meal, result);
      setText("");
      setStatus("result");
    } catch {
      // Fail-soft: keep the text so the meal can be retried.
      setStatus("empty");
    }
  }

  const processing = status === "processing";

  return (
    <form
      className={"loginput" + (processing ? " on" : "")}
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <input
        className="loginput-field"
        value={text}
        placeholder="what did you eat?"
        disabled={processing}
        aria-label="what did you eat?"
        onChange={(e) => {
          setText(e.target.value);
          // Any keystroke clears a lingering confirmation.
          if (status === "result") setStatus("empty");
        }}
      />
      {status === "result" && (
        <span className="loginput-done" role="status">
          logged
        </span>
      )}
      <button type="submit" className="loginput-btn" disabled={processing}>
        {processing ? "Logging…" : "Log"}
      </button>
    </form>
  );
}
