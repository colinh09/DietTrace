"use client";

// First-run onboarding — a conversational flow, not a form. It always runs for a
// new user (and again after a reset). Two paths from the first screen:
//   • "See it in action" → pick a demo persona → seed it → land on the log screen.
//   • "Set up your own"   → the nutritionist chats: a short series of skippable
//      questions (tap to answer), ending with a freeform "tell me about your
//      lifestyle / goals" — saved as the corrector's standing context. The body
//      answers compute the daily targets (deterministic, instant, no spend).
// Whole own-data path is under a minute. The Macros tab edits targets afterward.
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Pencil, Play, Send, Sparkle } from "lucide-react";
import {
  postMacrosPlan,
  postMacrosSave,
  seedDemo,
  setProfile,
  type MacroActivity,
  type MacroGoal,
  type MacroSex,
  type SeedDemoResult,
} from "@/lib/api";
import { markOnboarded } from "@/lib/onboarding";
import { PERSONA_INPUTS, setSetup, type ProfileInputs } from "@/lib/setup";
import { SeededModal } from "@/components/seeded-modal";

// One scripted question. `chips` = tap to answer, `number` = inline numeric input,
// `text` = the closing freeform box. Every question is skippable.
interface Step {
  key: "gender" | "weight" | "age" | "height" | "activity" | "goal" | "lifestyle";
  q: string;
  kind: "chips" | "number" | "text";
  options?: { value: string; label: string }[];
  unit?: string;
}

const STEPS: Step[] = [
  {
    key: "gender",
    q: "Hey — I'm your nutritionist. First up: what's your gender? It helps me size your daily targets.",
    kind: "chips",
    options: [
      { value: "male", label: "Male" },
      { value: "female", label: "Female" },
    ],
  },
  { key: "weight", q: "Got it. Roughly what do you weigh?", kind: "number", unit: "kg" },
  { key: "age", q: "How old are you? (optional)", kind: "number", unit: "yr" },
  { key: "height", q: "And your height? (optional)", kind: "number", unit: "cm" },
  {
    key: "activity",
    q: "How active are you most days?",
    kind: "chips",
    options: [
      { value: "light", label: "Lightly" },
      { value: "moderate", label: "Moderately" },
      { value: "very_active", label: "Very active" },
    ],
  },
  {
    key: "goal",
    q: "What are you going for right now?",
    kind: "chips",
    options: [
      { value: "cut", label: "Lose" },
      { value: "maintain", label: "Maintain" },
      { value: "bulk", label: "Gain" },
    ],
  },
  {
    key: "lifestyle",
    q: "Last one — tell me about your lifestyle, eating habits, goals… anything that helps me read your meals. (You can skip this.)",
    kind: "text",
  },
];

type Answers = Record<string, string | number>;
type Msg = { role: "agent" | "user"; text: string };

export function Onboarding({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState<"choose" | "chat">("choose");
  const [busy, setBusy] = useState(false);

  // Chat state.
  const [stepIndex, setStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});
  const [transcript, setTranscript] = useState<Msg[]>([]);
  const [numDraft, setNumDraft] = useState("");
  const [textDraft, setTextDraft] = useState("");
  // After a demo seed: the persona context preview shown before landing.
  const [seedResult, setSeedResult] = useState<SeedDemoResult | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Keep the latest message in view as the conversation grows.
  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [transcript]);

  // ── Seed path ──────────────────────────────────────────────────────────────
  // Seed the persona, remember it as the active setup, then show the context
  // preview (what was loaded + the learning state) before dropping into the app.
  const seed = async (persona: string) => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await seedDemo(undefined, persona);
      setSetup({
        kind: "persona",
        personaKey: persona,
        inputs: PERSONA_INPUTS[persona] ?? {},
        result,
      });
      markOnboarded();
      setSeedResult(result);
    } catch {
      // fail-soft — drop straight into the app
      markOnboarded();
      onDone();
    } finally {
      setBusy(false);
    }
  };

  // ── Own-data path: the guided chat ───────────────────────────────────────────
  const startChat = () => {
    setTranscript([{ role: "agent", text: STEPS[0].q }]);
    setStepIndex(0);
    setPhase("chat");
  };

  // Record an answer (or a skip), echo it, and advance to the next question.
  const advance = (partial: Answers, userLabel: string) => {
    const merged = { ...answers, ...partial };
    setAnswers(merged);
    const next = stepIndex + 1;
    setTranscript((t) => [
      ...t,
      { role: "user", text: userLabel },
      ...(next < STEPS.length
        ? [{ role: "agent" as const, text: STEPS[next].q }]
        : []),
    ]);
    setNumDraft("");
    setStepIndex(next);
  };

  const submitNumber = (step: Step) => {
    const v = numDraft.trim();
    if (v) advance({ [step.key]: parseInt(v, 10) }, `${v} ${step.unit}`);
    else advance({}, "Skip");
  };

  // The closing freeform answer → finish (compute targets, save profile, done).
  const finish = async (final: Answers) => {
    setBusy(true);
    try {
      // Body answers → daily targets. Deterministic formula (ai_help: false) so
      // it's instant and free; blanks fall back to neutral defaults so the path
      // works even if everything was skipped. All editable later in Macros.
      const gender = (final.gender as MacroSex) ?? "male";
      const plan = await postMacrosPlan({
        sex: gender,
        weight_kg: (final.weight as number) ?? 75,
        age: (final.age as number) ?? 30,
        height_cm: (final.height as number) ?? (gender === "female" ? 164 : 178),
        activity: (final.activity as MacroActivity) ?? "moderate",
        goal: (final.goal as MacroGoal) ?? "maintain",
        ai_help: false,
      });
      await postMacrosSave(plan.targets, plan.rationale, plan.source);
    } catch {
      // keep going — defaults apply
    }
    const lifestyle =
      typeof final.lifestyle === "string" ? final.lifestyle.trim() : "";
    if (lifestyle) {
      try {
        await setProfile(lifestyle);
      } catch {
        // non-fatal — can be added later from "your context"
      }
    }
    // Remember what they actually entered (only the answered fields) so the
    // Macros editor and "Persona details" reflect their setup, not defaults.
    const inputs: ProfileInputs = {};
    if (final.gender) inputs.sex = final.gender as MacroSex;
    if (typeof final.weight === "number") inputs.weight_kg = final.weight;
    if (typeof final.age === "number") inputs.age = final.age;
    if (typeof final.height === "number") inputs.height_cm = final.height;
    if (final.activity) inputs.activity = final.activity as MacroActivity;
    if (final.goal) inputs.goal = final.goal as MacroGoal;
    setSetup({ kind: "own", inputs, lifestyle });
    markOnboarded();
    onDone();
  };

  const finishText = (text: string) => {
    const clean = text.trim();
    const merged = { ...answers, ...(clean ? { lifestyle: clean } : {}) };
    setAnswers(merged);
    setTranscript((t) => [...t, { role: "user", text: clean || "Skipped" }]);
    finish(merged);
  };

  const step = STEPS[stepIndex];

  return (
    <div className="ob-page">
      <div className="ob-card" role="dialog" aria-label="Welcome to DietTrace">
        <div className="ob-brand">
          <Sparkle size={16} fill="var(--accent)" color="var(--accent)" />
          <span className="brand-name">DietTrace</span>
        </div>

        {phase === "choose" ? (
          <>
            <h1 className="ob-title">Welcome</h1>
            <p className="ob-sub">
              Your AI nutritionist. Start from a ready-made demo, or set up your
              own in under a minute.
            </p>

            <div className="ob-choices">
              {/* See it in action → straight into the detailed persona chooser */}
              <button
                type="button"
                className="ob-choice ob-choice-own"
                disabled={busy}
                onClick={() => seed("runner")}
              >
                <span className="ob-choice-glyph">
                  <Play size={16} aria-hidden="true" />
                </span>
                <span className="ob-choice-body">
                  <span className="ob-choice-title">See it in action</span>
                  <span className="ob-choice-desc">
                    {busy ? "Loading…" : "Load a demo and explore the personas"}
                  </span>
                </span>
                <ArrowRight size={16} aria-hidden="true" />
              </button>

              {/* Set up your own → the chat */}
              <button
                type="button"
                className="ob-choice ob-choice-own"
                onClick={startChat}
              >
                <span className="ob-choice-glyph">
                  <Pencil size={16} aria-hidden="true" />
                </span>
                <span className="ob-choice-body">
                  <span className="ob-choice-title">Set up your own</span>
                  <span className="ob-choice-desc">
                    Chat with the agent — under a minute
                  </span>
                </span>
                <ArrowRight size={16} aria-hidden="true" />
              </button>
            </div>
          </>
        ) : (
          <div className="ob-chat">
            <div className="ob-progress mono">
              {Math.min(stepIndex + 1, STEPS.length)} / {STEPS.length}
            </div>
            <div className="ob-msgs">
              {transcript.map((m, i) => (
                <div className={"ob-msg " + m.role} key={i}>
                  {m.role === "agent" && (
                    <span className="ob-avatar" aria-hidden="true">
                      <Sparkle size={12} fill="var(--accent)" color="var(--accent)" />
                    </span>
                  )}
                  <span className="ob-bubble">{m.text}</span>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>

            {/* The current question's input dock */}
            {!busy && step?.kind === "chips" && (
              <div className="ob-chips">
                {step.options!.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    className="ob-chip"
                    onClick={() => advance({ [step.key]: o.value }, o.label)}
                  >
                    {o.label}
                  </button>
                ))}
                <button
                  type="button"
                  className="ob-chip ob-chip-skip"
                  onClick={() => advance({}, "Skip")}
                >
                  Skip
                </button>
              </div>
            )}

            {!busy && step?.kind === "number" && (
              <div className="ob-num-row">
                <div className="ob-num-input">
                  <input
                    value={numDraft}
                    inputMode="numeric"
                    autoFocus
                    aria-label={step.q}
                    placeholder="—"
                    onChange={(e) =>
                      setNumDraft(e.target.value.replace(/[^0-9]/g, ""))
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter") submitNumber(step);
                    }}
                  />
                  <span className="ob-num-unit">{step.unit}</span>
                </div>
                <button
                  type="button"
                  className="ob-send"
                  aria-label="send"
                  disabled={!numDraft}
                  onClick={() => submitNumber(step)}
                >
                  <Send size={16} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  className="ob-chip ob-chip-skip"
                  onClick={() => advance({}, "Skip")}
                >
                  Skip
                </button>
              </div>
            )}

            {step?.kind === "text" && (
              <div className="ob-text-row">
                <textarea
                  className="ob-textarea"
                  value={textDraft}
                  rows={3}
                  autoFocus
                  disabled={busy}
                  aria-label="your lifestyle, eating habits and goals"
                  placeholder="e.g. Marathon training, mostly plant-based — I keep carbs high on long-run days."
                  onChange={(e) => setTextDraft(e.target.value)}
                />
                <div className="ob-text-actions">
                  <button
                    type="button"
                    className="ob-chip ob-chip-skip"
                    disabled={busy}
                    onClick={() => finishText("")}
                  >
                    Skip
                  </button>
                  <button
                    type="button"
                    className="ob-btn-primary"
                    disabled={busy}
                    onClick={() => finishText(textDraft)}
                  >
                    {busy ? "Setting up…" : "Finish"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* After a demo seed: preview what was loaded, then land on the app. */}
      {seedResult && (
        <SeededModal
          result={seedResult}
          busy={busy}
          onReseed={(p) => seed(p)}
          onClose={onDone}
        />
      )}
    </div>
  );
}
