"use client";

// Free-form feedback for a logged meal — lets the user type a natural-language
// comment ("fries were smaller, maybe half") that DietTrace interprets and
// applies, then surfaces what it learned as a "DietTrace learned: …" panel
//. Sits alongside the existing gram-edit correction
// so both paths stay available.
import { useState } from "react";
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
      return `adjusted ${result.target_food} to ${((result.adjustment ?? 1) * 100).toFixed(0)}% of logged portion`;
    case "remove_item":
      return `removed ${result.target_food} from this meal`;
    case "add_item":
      return `added ${result.target_food}${result.adjustment != null ? ` (${Math.round(result.adjustment)} g)` : ""}`;
    case "standing_rule":
      return `standing preference saved: ${result.rationale || result.target_food}`;
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

  return (
    <div className="freeform-feedback">
      {status !== "done" && (
        <div className="freeform-input-row">
          <input
            className="freeform-input mono"
            type="text"
            placeholder="Anything off? (e.g. 'fries were smaller, maybe half')"
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
            className="correct-btn mono"
            onClick={() => void submit()}
            disabled={status === "loading" || !text.trim()}
          >
            {status === "loading" ? "thinking…" : "tell it"}
          </button>
        </div>
      )}
      {status === "error" && (
        <span className="correct-err">couldn&apos;t apply — try again</span>
      )}
      {status === "done" && result?.ok && (
        <div className="freeform-learned" aria-live="polite">
          <span className="freeform-learned-label mono">DietTrace learned:</span>
          <span className="freeform-learned-desc">{learnedLabel(result)}</span>
          {result.stored_as_preference && (
            <span className="freeform-pref-note dim">
              saved as a standing preference — applies to future meals
            </span>
          )}
        </div>
      )}
    </div>
  );
}
