"use client";

// The per-meal review step. Every logged meal asks
// "does this look about right?" — the user either confirms it (it becomes a
// held-out ground-truth datapoint, Input A) or says they'd change something,
// which opens the correction box (Input B). The two paths are mutually exclusive
// (XOR): correcting a meal drops it from the ground-truth set on the backend.
import { useState } from "react";
import { Check } from "lucide-react";
import { confirmMeal, type LoggedItem, type Nutrient } from "@/lib/api";
import { FreeformFeedback } from "@/components/freeform-feedback";
import { QuantityEditor } from "@/components/quantity-editor";

type Mode = "ask" | "tweaking" | "correcting" | "confirmed";

export function MealReview({
  mealId,
  mealText,
  perItem,
  totals,
  onCorrected,
}: {
  mealId?: number;
  mealText: string;
  perItem: LoggedItem[];
  totals: Nutrient[];
  onCorrected?: () => void;
}) {
  const [mode, setMode] = useState<Mode>("ask");
  const [saving, setSaving] = useState(false);

  const confirm = () => {
    if (saving) return;
    setSaving(true);
    confirmMeal(mealText, perItem, totals)
      .then(() => setMode("confirmed"))
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  if (mode === "confirmed") {
    return (
      <div className="review-confirmed">
        <Check size={14} aria-hidden="true" />
        <span>
          Saved as a reference — DietTrace now checks itself against this meal.
        </span>
        <button
          type="button"
          className="review-undo"
          onClick={() => setMode("correcting")}
        >
          actually, I&apos;d change something
        </button>
      </div>
    );
  }

  return (
    <div className="review">
      <div className="review-head">
        <span className="review-q">Does this look about right?</span>
        <span className="review-sub">
          A quick check so DietTrace only learns from meals you&apos;ve vetted.
        </span>
      </div>

      {mode === "ask" && (
        <div className="review-actions">
          <button
            type="button"
            className="review-yes"
            onClick={confirm}
            disabled={saving}
          >
            {saving ? "saving…" : "Yes, looks right"}
          </button>
          <button
            type="button"
            className="review-tweak"
            onClick={() => setMode("tweaking")}
          >
            Close — let me tweak a portion
          </button>
          <button
            type="button"
            className="review-no"
            onClick={() => setMode("correcting")}
          >
            No, something&apos;s off
          </button>
        </div>
      )}
      {mode === "tweaking" && (
        <QuantityEditor
          mealText={mealText}
          perItem={perItem}
          onConfirmed={() => setMode("confirmed")}
          onCancel={() => setMode("ask")}
        />
      )}
      {mode === "correcting" && (
        <FreeformFeedback
          mealId={mealId}
          mealText={mealText}
          perItem={perItem}
          onFeedbackApplied={() => onCorrected?.()}
        />
      )}
    </div>
  );
}
