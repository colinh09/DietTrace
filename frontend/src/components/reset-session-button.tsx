"use client";

// "Reset" affordance — wipes the current user's meals, goals, and everything
// DietTrace has learned about them (POST /session/reset), then fires onReset so
// the page refreshes to a clean slate. Two-click confirm guards the data loss.
import { useState } from "react";
import { resetSession } from "@/lib/api";

interface ResetSessionButtonProps {
  onReset?: () => void;
}

export function ResetSessionButton({ onReset }: ResetSessionButtonProps) {
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const handleClick = () => {
    if (busy) return;
    if (!confirming) {
      setConfirming(true);
      return;
    }
    setBusy(true);
    // Wipe the server-side data, then ALWAYS fire onReset — even if the call
    // failed — so resetting reliably brings the user back to onboarding rather
    // than silently doing nothing on a hiccup.
    resetSession()
      .catch(() => {})
      .finally(() => {
        setBusy(false);
        setConfirming(false);
        onReset?.();
      });
  };

  return (
    <button
      type="button"
      className={"nav-item reset-session-btn" + (confirming ? " confirming" : "")}
      onClick={handleClick}
      onBlur={() => setConfirming(false)}
      disabled={busy}
      title="Clear your meals, goals, and learned preferences"
    >
      {busy ? "Resetting…" : confirming ? "Reset everything?" : "Reset"}
    </button>
  );
}
