"use client";

// The account avatar + dropdown menu. The navbar is constant chrome: the
// destructive Reset and the modal-opener "Persona details"
// move OUT of the primary tabs and fold in here, behind the avatar. The two
// surfaces they open (the persona recap, the Reset confirmation) are rendered at
// this level — siblings of the dropdown — so closing the menu never unmounts an
// open modal.
import { useEffect, useRef, useState } from "react";
import { LogOut, RotateCcw, User } from "lucide-react";
import { getSetup, type Setup } from "@/lib/setup";
import { useAuth } from "@/lib/auth";
import { clearAnon } from "@/lib/auth-gate";
import { RecapModal } from "@/components/recap-modal";
import { ResetDialog } from "@/components/reset-dialog";
import { Modal } from "@/components/modal";

// A short, friendly account label from the saved onboarding snapshot. Persona
// demos read by their key; a user's own setup reads as "You"; nothing saved yet
// also falls back to "You" (the avatar still works pre-onboarding).
function accountLabel(setup: Setup | null): { name: string; sub: string } {
  if (setup?.kind === "persona") {
    const key = setup.personaKey.replace(/[-_]/g, " ");
    return { name: key.replace(/\b\w/g, (c) => c.toUpperCase()), sub: "Demo persona" };
  }
  if (setup?.kind === "own") return { name: "You", sub: "Your setup" };
  return { name: "You", sub: "Guest" };
}

export function AccountMenu({
  onViewDay,
  onReset,
  onAuthChange,
}: {
  // Navigate the page to a given ISO day (the persona recap's "see the dataset").
  onViewDay?: (iso: string) => void;
  // Fired after a confirmed reset wipes the user's data.
  onReset?: () => void;
  // Fired after a sign-in/out so the page can reload data for the new bucket.
  onAuthChange?: () => void;
}) {
  const { user, configured, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [personaOpen, setPersonaOpen] = useState(false);
  const [setup, setSetupState] = useState<Setup | null>(null);
  const [resetOpen, setResetOpen] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const acctRef = useRef<HTMLDivElement>(null);

  // Close the menu on an outside click (the modals carry their own scrim).
  useEffect(() => {
    if (!menuOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (acctRef.current && !acctRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  // A signed-in Firebase user labels the menu; otherwise fall back to the saved
  // onboarding snapshot (persona / own setup / anonymous).
  const label = user
    ? {
        name: user.displayName ?? user.email ?? "Account",
        sub: user.email ?? "Signed in",
      }
    : accountLabel(setup ?? getSetup());

  const openPersona = () => {
    setSetupState(getSetup());
    setPersonaOpen(true);
    setMenuOpen(false);
  };
  const openReset = () => {
    setResetOpen(true);
    setMenuOpen(false);
  };

  // Sign in/out from inside the menu. Guarded so a missed Firebase config or a
  // closed popup never throws; the page refetches data for the new bucket after.
  const runAuth = async (fn: () => Promise<void>) => {
    if (authBusy) return;
    setMenuOpen(false);
    setAuthBusy(true);
    try {
      await fn();
      onAuthChange?.();
    } catch {
      /* popup closed / network — leave state as-is, the user can retry */
    } finally {
      setAuthBusy(false);
    }
  };

  // Once you're on the food-logging screen you're always "logged in" (Google or
  // anonymous), so the menu always offers Sign out. A real user signs out of
  // Firebase; an anonymous user forgets the "continue anonymous" choice and
  // reloads back to the sign-in gate.
  const handleSignOut = () => {
    if (user) {
      runAuth(signOut);
      return;
    }
    setMenuOpen(false);
    clearAnon();
    window.location.reload();
  };

  return (
    <>
      <div className="acct" ref={acctRef}>
        <button
          type="button"
          className="avatar"
          aria-label="Account"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          {label.name.charAt(0).toUpperCase()}
        </button>
        {menuOpen && (
          <div className="acct-menu" role="menu">
            <div className="acct-menu-head">
              <span className="acct-menu-avatar" aria-hidden="true">
                {label.name.charAt(0).toUpperCase()}
              </span>
              <span className="acct-menu-id">
                <span className="acct-menu-name">{label.name}</span>
                <span className="acct-menu-sub">{label.sub}</span>
              </span>
            </div>
            <button
              type="button"
              className="acct-menu-item"
              role="menuitem"
              onClick={openPersona}
            >
              <User size={16} className="acct-menu-ic" aria-hidden="true" />
              Your details
            </button>
            {configured && (
              <>
                <div className="acct-menu-sep" />
                <button
                  type="button"
                  className="acct-menu-item"
                  role="menuitem"
                  onClick={handleSignOut}
                  disabled={authBusy}
                >
                  <LogOut size={16} className="acct-menu-ic" aria-hidden="true" />
                  Sign out
                </button>
              </>
            )}
            <div className="acct-menu-sep" />
            <button
              type="button"
              className="acct-menu-item danger"
              role="menuitem"
              onClick={openReset}
            >
              <RotateCcw size={16} className="acct-menu-ic" aria-hidden="true" />
              Reset everything…
            </button>
          </div>
        )}
      </div>

      {personaOpen && setup && (
        <RecapModal
          setup={setup}
          onViewDay={onViewDay}
          onClose={() => setPersonaOpen(false)}
        />
      )}
      {personaOpen && !setup && (
        <Modal onClose={() => setPersonaOpen(false)} labelledBy="setup-title">
          <div className="su">
            <span className="su-eyebrow mono">Your setup</span>
            <h2 id="setup-title" className="su-title">
              Nothing set up yet
            </h2>
            <p className="su-sub">
              Reset to run onboarding again — load a demo persona or set up your
              own.
            </p>
            <div className="su-actions">
              <button
                type="button"
                className="su-done"
                onClick={() => setPersonaOpen(false)}
              >
                Got it
              </button>
            </div>
          </div>
        </Modal>
      )}
      {resetOpen && (
        <ResetDialog onClose={() => setResetOpen(false)} onReset={onReset} />
      )}
    </>
  );
}
