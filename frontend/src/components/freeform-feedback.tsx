"use client";

// Free-form feedback for a logged meal — lets the user type a natural-language
// comment ("fries were smaller, maybe half") that DietTrace interprets and
// applies, then surfaces what it learned as a "DietTrace learned: …" panel
//. Sits alongside the existing gram-edit correction
// so both paths stay available.
import { useState } from "react";
import { Check } from "lucide-react";
import type { FreeformFeedbackResult, LoggedItem } from "@/lib/api";
import { submitFreeformFeedback } from "@/lib/api";

interface Props {
  mealId?: number;
  mealText?: string;
  perItem?: LoggedItem[];
  onFeedbackApplied?: (result: FreeformFeedbackResult) => void;
}

function learnedLabel(result: FreeformFeedbackResult): string {
  switch (result.kind) {
    case "portion_adjust":
      // Absolute fix ("about 30 grams") sets the portion directly; a relative
      // fix ("half") scales it — label each in its own terms.
      return result.target_grams != null
        ? `set ${result.target_food} to ${Math.round(result.target_grams)} g`
        : `scaled ${result.target_food} to ${Math.round((result.adjustment ?? 1) * 100)}% of the logged portion`;
    case "remove_item":
      return `removed ${result.target_food} from this meal`;
    case "add_item":
      return `added ${result.target_food}${result.adjustment != null ? ` (${Math.round(result.adjustment)} g)` : ""}`;
    case "standing_rule":
      return result.rationale || result.target_food || "";
    default:
      return result.rationale || String(result.kind ?? "");
  }
}

export function FreeformFeedback({
  mealId,
  mealText,
  perItem,
  onFeedbackApplied,
}: Props) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">(
    "idle",
  );
  const [result, setResult] = useState<FreeformFeedbackResult | null>(null);

  async function submit() {
    const trimmed = text.trim();
    if (!trimmed) return;
    setStatus("loading");
    try {
      const res = await submitFreeformFeedback({
        meal_id: mealId ?? null,
        meal_text: mealText ?? "",
        feedback_text: trimmed,
        current_items: perItem ?? [],
      });
      setResult(res);
      setStatus("done");
      setText("");
      if (res.ok) onFeedbackApplied?.(res);
    } catch {
      setStatus("error");
    }
  }

  const reset = () => {
    setStatus("idle");
    setResult(null);
  };

  return (
    <div className="freeform-feedback">
      {status !== "done" && (
        <>
          <div className="freeform-hint">
            Tell DietTrace what to fix in plain words — it corrects this meal and
            learns your style.
          </div>
          <div className="freeform-input-row">
            <input
              className="freeform-input"
              type="text"
              placeholder=""
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void submit();
              }}
              disabled={status === "loading"}
              aria-label="free-form feedback"
            />
            <button
              type="button"
              className="freeform-btn"
              onClick={() => void submit()}
              disabled={status === "loading" || !text.trim()}
            >
              {status === "loading" ? "thinking…" : "tell it"}
            </button>
          </div>
        </>
      )}
      {status === "error" && (
        <span className="freeform-err">couldn&apos;t apply — try again</span>
      )}
      {status === "done" && result?.ok && (
        <div className="freeform-learned" aria-live="polite">
          <span className="freeform-learned-label mono">✦ DietTrace learned</span>
          <span className="freeform-learned-desc">{learnedLabel(result)}</span>

          {/* Observability: the exact backend + Arize steps this correction took,
              so it's clear how feedback becomes ground truth the agent re-tests on. */}
          {result.kind === "standing_rule" ? (
            <span className="freeform-pref-note">
              Saved as a standing rule — DietTrace applies it to your future meals
              right away.
            </span>
          ) : (
            <>
              <ol className="freeform-process">
                <li className="fp-step">
                  <Check size={12} className="fp-check" /> Read your words (no
                  fiddly gram editing)
                </li>
                <li className="fp-step">
                  <Check size={12} className="fp-check" /> Recalculated this meal
                  &amp; the day total
                </li>
                <li className="fp-step">
                  <Check size={12} className="fp-check" /> Saved as a confirmed example
                  {result.corrections != null
                    ? ` — correction #${result.corrections}`
                    : ""}
                </li>
                <li className={"fp-step" + (result.added_to_arize ? "" : " fp-muted")}>
                  <Check size={12} className="fp-check" />{" "}
                  {result.added_to_arize
                    ? "Logged to Phoenix as a confirmed example"
                    : "Phoenix logging skipped (not configured)"}
                </li>
              </ol>
              <span className="freeform-process-foot">
                Open the accuracy panel and tap <b>Update</b> to see DietTrace
                re-check itself on what you just taught it.
              </span>
            </>
          )}
        </div>
      )}
      {status === "done" && result && !result.ok && (
        <div className="freeform-learned warn" aria-live="polite">
          <span className="freeform-learned-desc">
            Couldn&apos;t read that one — try rephrasing.
          </span>
          <button type="button" className="freeform-again" onClick={reset}>
            try again
          </button>
        </div>
      )}
    </div>
  );
}
