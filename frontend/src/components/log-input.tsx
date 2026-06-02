"use client";

// The inline log input: an italic "what did you eat?" field. On Enter or the Log
// button it hands the text up via `onSubmit`; the page streams it to /log/stream
// and shows the agent's work live. `busy` is driven by the page while a
// stream is in flight, disabling the field until the meal settles.
//
// A mic button drives the browser Web Speech API: speaking
// transcribes into the field so the existing submit can send it. It fails soft —
// when the browser has no SpeechRecognition the button is simply absent.
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Mic } from "lucide-react";

// Support never changes within a session, so there is nothing to subscribe to.
const noopSubscribe = () => () => {};

// Minimal shape of the bits of the Web Speech API we touch. The constructor
// lives under `SpeechRecognition` (standard) or `webkitSpeechRecognition`.
type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function getRecognitionCtor(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function LogInput({
  onSubmit,
  busy,
}: {
  onSubmit: (text: string) => void;
  busy: boolean;
}) {
  const [text, setText] = useState("");
  // Whether the browser offers speech recognition. Read via useSyncExternalStore
  // so the server snapshot (no API) and the client snapshot stay consistent
  // through hydration — the mic simply doesn't appear when unsupported (fail-soft).
  const voiceSupported = useSyncExternalStore(
    noopSubscribe,
    () => getRecognitionCtor() !== null,
    () => false,
  );
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  // Stop any in-flight recognition if the component unmounts mid-listen.
  useEffect(() => () => recognitionRef.current?.stop(), []);

  function submit() {
    const meal = text.trim();
    if (!meal || busy) return;
    setText("");
    onSubmit(meal);
  }

  function startListening() {
    const Ctor = getRecognitionCtor();
    if (!Ctor || busy || listening) return;
    const recognition = new Ctor();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript ?? "";
      if (transcript) setText(transcript.trim());
    };
    recognition.onerror = () => setListening(false);
    recognition.onend = () => setListening(false);
    recognitionRef.current = recognition;
    setListening(true);
    recognition.start();
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
      {voiceSupported && !busy && (
        <button
          type="button"
          className={"loginput-mic" + (listening ? " on" : "")}
          aria-label="voice input"
          aria-pressed={listening}
          onClick={startListening}
        >
          <Mic size={16} aria-hidden />
        </button>
      )}
      <button type="submit" className="loginput-btn" disabled={busy}>
        {busy ? "Logging…" : "Log"}
      </button>
    </form>
  );
}
