"use client";

// The Reset confirmation as a PROPER modal (: kill the in-place
// "Reset everything?" morph in the navbar). Wipes the current user's meals,
// goals, and learned preferences (POST /session/reset), then fires onReset so the
// page falls back to a clean slate / onboarding. ALWAYS fires onReset — even on a
// failed call — so a hiccup never strands the user mid-reset.
import { useState } from "react";
import { resetSession } from "@/lib/api";
import { Modal } from "@/components/modal";

export function ResetDialog({
  onClose,
  onReset,
}: {
  onClose: () => void;
  onReset?: () => void;
}) {
  const [busy, setBusy] = useState(false);

  const commit = () => {
    if (busy) return;
    setBusy(true);
    resetSession()
      .catch(() => {})
      .finally(() => {
        setBusy(false);
        onReset?.();
        onClose();
      });
  };

  return (
    <Modal onClose={onClose} labelledBy="reset-title">
      <div className="reset-dialog">
        <div className="reset-dialog-eyebrow mono">Reset</div>
        <h2 id="reset-title" className="reset-dialog-title display">
          Reset everything?
        </h2>
        <p className="reset-dialog-body">
          This permanently clears your meals, goals, and everything DietTrace has
          learned about you, then restarts onboarding. This can&apos;t be undone.
        </p>
        <div className="reset-dialog-actions">
          <button
            type="button"
            className="btn-ghost"
            onClick={onClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn-danger"
            onClick={commit}
            disabled={busy}
          >
            {busy ? "Resetting…" : "Reset"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
