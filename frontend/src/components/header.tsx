"use client";

// The app's top navbar: the leaf wordmark on the left, the primary view tabs
// (Today · Macros · Overview) right-aligned, and the account avatar on the far
// right. Per  the navbar is CONSTANT chrome — the modal-opener
// "Persona details" and the destructive "Reset" no longer sit among the tabs;
// they fold into the avatar's account menu. The day/calendar navigation lives in
// the day-summary card below, not here. The leaf is the brand
// placeholder until the final apple "trace" mark lands.
import { Leaf } from "lucide-react";
import { AccountMenu } from "@/components/account-menu";

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
        <Leaf size={18} color="var(--accent)" strokeWidth={1.7} />
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
      </nav>
      <div className="hdr-end">
        <AccountMenu
          onViewDay={onViewDay}
          onReset={onReset ?? onSeeded}
          onAuthChange={onAuthChange}
        />
      </div>
    </header>
  );
}
