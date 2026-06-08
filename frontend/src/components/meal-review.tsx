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
import type { AgentActivity } from "@/components/agent-decision";
import { QuantityEditor } from "@/components/quantity-editor";

type Mode = "ask" | "reviewing" | "tweaking" | "correcting" | "confirmed";

export function MealReview({
  mealId,
  mealText,
  perItem,
  totals,
  onCorrected,
  onAgentEvent,
}: {
  mealId?: number;
  mealText: string;
  perItem: LoggedItem[];
  totals: Nutrient[];
  onCorrected?: () => void;
  onAgentEvent?: AgentActivity;
}) {
  const [mode, setMode] = useState<Mode>("ask");
  const [saving, setSaving] = useState(false);

  const confirm = () => {
    if (saving) return;
    setSaving(true);
    confirmMeal(mealText, perItem, totals)
      .then((res) => {
        setMode("confirmed");
        // Live: refresh the state counts AND drop an entry into the activity feed.
        onCorrected?.();
        onAgentEvent?.({
          op: "add_dataset_point",
          reason: "you confirmed it — added to your answer key",
          mealText,
          phoenix: "wrote 1 point to your Phoenix dataset",
        });
        // Growing the held-out set can tip the supervisor into a retune.
        if (res?.supervisor?.op === "retune") {
          onAgentEvent?.({
            op: "retune",
            reason: res.supervisor.reason,
            mealText,
            phoenix: res.supervisor.phoenix,
          });
        }
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  // Terminal, locked state — once confirmed it's an answer key; no more changes
  // or undos (a later change would un-confirm it and break the XOR with feedback).
  if (mode === "confirmed") {
    return (
      <div className="review-confirmed">
        <Check size={14} aria-hidden="true" />
        <span>
          Confirmed — saved as an answer key. DietTrace will check its future
          updates against this meal, but never peeks at it while learning.
        </span>
      </div>
    );
  }

  return (
    <div className="review">
      {(mode === "ask" || mode === "reviewing") && (
        <div className="review-head">
          <span className="review-q">
            {mode === "ask" ? "Does this look right?" : "Would you change anything?"}
          </span>
          <span className="review-sub">
            {mode === "ask"
              ? "A quick check so DietTrace only learns from meals you've confirmed are right."
              : "Adjust a portion if something's off — otherwise confirm it as your answer key."}
          </span>
        </div>
      )}

      {mode === "ask" && (
        <div className="review-actions">
          <button
            type="button"
            className="review-yes"
            onClick={() => setMode("reviewing")}
          >
            Looks right
          </button>
          <button
            type="button"
            className="review-no"
            onClick={() => setMode("correcting")}
          >
            Something&apos;s off
          </button>
        </div>
      )}
      {mode === "reviewing" && (
        <div className="review-actions">
          <button
            type="button"
            className="review-yes"
            onClick={confirm}
            disabled={saving}
          >
            {saving ? "saving…" : "No — confirm it"}
          </button>
          <button
            type="button"
            className="review-no"
            onClick={() => setMode("tweaking")}
          >
            Adjust a portion
          </button>
        </div>
      )}
      {mode === "tweaking" && (
        <QuantityEditor
          mealText={mealText}
          perItem={perItem}
          onConfirmed={() => setMode("confirmed")}
          onCancel={() => setMode("reviewing")}
        />
      )}
      {mode === "correcting" && (
        <FreeformFeedback
          mealId={mealId}
          mealText={mealText}
          perItem={perItem}
          onFeedbackApplied={(res) => {
            onCorrected?.();
            onAgentEvent?.({
              op: "bank_feedback",
              reason: res.stored_as_preference
                ? "learned a rule from your correction"
                : "saved your correction to learn from on the next update",
              mealText,
            });
            // Feedback is the primary retune trigger — if this correction tipped
            // the supervisor over, run the gated eval now.
            if (res.supervisor?.op === "retune") {
              onAgentEvent?.({
            op: "retune",
            reason: res.supervisor.reason,
            mealText,
            phoenix: res.supervisor.phoenix,
          });
            }
          }}
        />
      )}
    </div>
  );
}
