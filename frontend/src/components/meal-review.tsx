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
import { QuantityEditor, type PortionChange } from "@/components/quantity-editor";

type Mode = "ask" | "reviewing" | "tweaking" | "correcting" | "confirmed";

export function MealReview({
  mealId,
  mealText,
  perItem,
  totals,
  hasFeedback = false,
  hasConfirmation = false,
  onCorrected,
  onAgentEvent,
}: {
  mealId?: number;
  mealText: string;
  perItem: LoggedItem[];
  totals: Nutrient[];
  // The meal already has a saved correction (persisted) — show the saved state,
  // not the "does this look right?" prompt (XOR with the confirmed/dataset path).
  hasFeedback?: boolean;
  // The user already confirmed this meal (it's a held-out dataset point) — show the
  // confirmed state instead of re-asking.
  hasConfirmation?: boolean;
  onCorrected?: () => void;
  onAgentEvent?: AgentActivity;
}) {
  const [mode, setMode] = useState<Mode>("ask");
  const [saving, setSaving] = useState(false);
  // Portions changed via "Adjust a portion" — shown in the confirmed message.
  const [changes, setChanges] = useState<PortionChange[]>([]);

  // Shared post-confirm work, run for BOTH a direct confirm and an adjusted-portion
  // confirm (the QuantityEditor) so neither path skips it: lock the UI, refresh the
  // state counts + history (so the meal becomes a dataset point), and drop the
  // dataset-point entry (+ any triggered retune) into the activity feed.
  const afterConfirm = (
    res: Awaited<ReturnType<typeof confirmMeal>>,
    edits: PortionChange[] = [],
  ) => {
    setMode("confirmed");
    setChanges(edits);
    onCorrected?.();
    onAgentEvent?.({
      op: "add_dataset_point",
      // No reason line — the "Added to your dataset" label already says it; a
      // second identical line just reads as duplication.
      reason: "",
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
  };

  const confirm = () => {
    if (saving) return;
    setSaving(true);
    confirmMeal(mealText, perItem, totals)
      .then(afterConfirm)
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  // Terminal, locked state — once confirmed it's in your dataset; no more changes
  // or undos (a later change would un-confirm it and break the XOR with feedback).
  if (mode === "confirmed") {
    return (
      <div className="review-confirmed">
        <Check size={14} aria-hidden="true" />
        <div className="review-confirmed-body">
          <p>Confirmed — saved to your dataset.</p>
          {changes.length > 0 && (
            <p>
              Updated{" "}
              {changes.map((c) => `${c.food} to ${c.grams} g`).join(", ")}.
            </p>
          )}
          <p>
            DietTrace will check its future updates against this meal, but never
            peeks at it while learning.
          </p>
        </div>
      </div>
    );
  }

  // Persisted confirmation: the user already confirmed this meal into their dataset,
  // so show the confirmed state instead of re-asking (XOR with feedback).
  if (hasConfirmation && mode === "ask") {
    return (
      <div className="review-confirmed">
        <Check size={14} aria-hidden="true" />
        <div className="review-confirmed-body">
          <p>Confirmed — saved to your dataset.</p>
          <p>
            DietTrace checks its updates against this meal, but never learns from it.
          </p>
        </div>
      </div>
    );
  }

  // Persisted feedback: this meal was already corrected (not a dataset point), so
  // don't re-ask — show the saved state, matching the dataset-point/confirmed path.
  if (hasFeedback && mode === "ask") {
    return (
      <div className="review-confirmed review-feedback">
        <Check size={14} aria-hidden="true" />
        <div className="review-confirmed-body">
          <p>Feedback saved.</p>
          <p>DietTrace will fold it into your agent on its next update.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="review">
      {mode === "reviewing" && (
        <button
          type="button"
          className="freeform-back"
          onClick={() => setMode("ask")}
        >
          ← Back
        </button>
      )}
      {(mode === "ask" || mode === "reviewing") && (
        <div className="review-head">
          <span className="review-q">
            {mode === "ask" ? "Does this look right?" : "Would you change anything?"}
          </span>
          <span className="review-sub">
            {mode === "ask"
              ? "A quick check so DietTrace only learns from meals you've confirmed are right."
              : "Adjust a portion if something's off — otherwise confirm it for your dataset."}
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
          mealId={mealId}
          perItem={perItem}
          onConfirmed={afterConfirm}
          onCancel={() => setMode("reviewing")}
        />
      )}
      {mode === "correcting" && (
        <FreeformFeedback
          mealId={mealId}
          mealText={mealText}
          perItem={perItem}
          onBack={() => setMode("ask")}
          onFeedbackApplied={(res) => {
            onCorrected?.();
            onAgentEvent?.({
              op: "bank_feedback",
              reason: "To be used to refine your DietTrace agent!",
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
