"use client";

// The app's top navbar: ✦ DietTrace on the left, then evenly-spaced tabs
// (Today · Macros · Overview · Persona details · Reset), and the auth control on
// the far right. The day/calendar navigation lives in the day-summary card below,
// not here.
import { Sparkle } from "lucide-react";
import { SetupDetailsButton } from "@/components/setup-details-button";
import { ResetSessionButton } from "@/components/reset-session-button";
import { AuthButton } from "@/components/auth-button";

interface HeaderProps {
  // The viewed day — the seed uses it as the reference for "today".
  date: Date;
  // Open the combined Accuracy + Trust "Overview" page.
  onOpenOverview?: () => void;
  // Open the macro editor ("Set your targets") modal.
  onOpenMacros?: () => void;
  // Called after POST /demo/seed completes so the page can refresh its data.
  onSeeded?: () => void;
  // Navigate the page to a given ISO day (the seed modal's "see the dataset").
  onViewDay?: (iso: string) => void;
  // Called after POST /session/reset wipes the user's data to a clean slate.
  onReset?: () => void;
  // Called after sign-in/out so the page reloads data for the new user bucket.
  onAuthChange?: () => void;
}

export function Header({
  onOpenOverview,
  onOpenMacros,
  onSeeded,
  onViewDay,
  onReset,
  onAuthChange,
}: HeaderProps) {
  return (
    <header className="hdr">
      <div className="brand">
        <Sparkle size={16} fill="var(--accent)" color="var(--accent)" />
        <span className="brand-name">DietTrace</span>
      </div>
      <nav className="hdr-nav" aria-label="Primary">
        <button type="button" className="nav-item active">
          Today
        </button>
        <button type="button" className="nav-item" onClick={() => onOpenMacros?.()}>
          Macros
        </button>
        <button type="button" className="nav-item" onClick={() => onOpenOverview?.()}>
          Overview
        </button>
        <SetupDetailsButton onViewDay={onViewDay} />
        <ResetSessionButton onReset={onReset ?? onSeeded} />
      </nav>
      <div className="hdr-end">
        <AuthButton onAuthChange={onAuthChange} />
      </div>
    </header>
  );
}
