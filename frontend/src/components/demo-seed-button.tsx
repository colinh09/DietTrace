"use client";

// "See it in action" affordance. Calls POST /demo/seed
// to populate the current user's history with canned meals + demo macro targets,
// then fires onSeeded so the page can refresh its history and analysis band.
import { useState } from "react";
import { seedDemo } from "@/lib/api";

interface DemoSeedButtonProps {
  onSeeded?: () => void;
}

export function DemoSeedButton({ onSeeded }: DemoSeedButtonProps) {
  const [busy, setBusy] = useState(false);

  const handleClick = () => {
    if (busy) return;
    setBusy(true);
    seedDemo()
      .then(() => onSeeded?.())
      .catch(() => {})
      .finally(() => setBusy(false));
  };

  return (
    <button
      type="button"
      className="nav-item demo-seed-btn"
      onClick={handleClick}
      disabled={busy}
    >
      {busy ? "Loading…" : "See it in action"}
    </button>
  );
}
