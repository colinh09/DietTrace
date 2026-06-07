"use client";

// Navbar "Persona details" — opens a READ-ONLY recap of the account: the seeded
// persona (or the user's own setup), their macros, what the agent knows/learned,
// and how it's doing on their meals. No persona switcher — changing the demo
// requires a Reset (which re-runs onboarding).
import { useState } from "react";
import { getSetup, type Setup } from "@/lib/setup";
import { RecapModal } from "@/components/recap-modal";
import { Modal } from "@/components/modal";

interface SetupDetailsButtonProps {
  // Navigate the page to a given ISO day (the recap's "see the dataset" link).
  onViewDay?: (iso: string) => void;
}

export function SetupDetailsButton({ onViewDay }: SetupDetailsButtonProps) {
  const [open, setOpen] = useState(false);
  const [setup, setSetupState] = useState<Setup | null>(null);

  const openDetails = () => {
    setSetupState(getSetup());
    setOpen(true);
  };
  const close = () => setOpen(false);

  return (
    <>
      <button
        type="button"
        className="nav-item"
        aria-label="Persona details"
        onClick={openDetails}
      >
        Persona details
      </button>

      {open && setup && (
        <RecapModal setup={setup} onViewDay={onViewDay} onClose={close} />
      )}

      {open && !setup && (
        <Modal onClose={close} labelledBy="setup-title">
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
              <button type="button" className="su-done" onClick={close}>
                Got it
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
