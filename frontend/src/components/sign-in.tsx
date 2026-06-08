"use client";

// The dedicated sign-in screen — the app's entry gate when Firebase is wired.
// Same design language as onboarding (serif display, sage accent, single card):
// "Continue with Google" to keep a log across devices, or "Continue without an
// account" to use DietTrace anonymously (everything works either way). When
// Firebase isn't configured the Google option is hidden and the anonymous path
// is the only one — so the screen never crashes and never dead-ends.
import { useState } from "react";
import { Sparkle } from "lucide-react";
import { useAuth } from "@/lib/auth";

// Google's "G" mark — inline so it needs no asset and inherits sizing.
function GoogleMark() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"
      />
    </svg>
  );
}

export function SignIn({ onContinueAnon }: { onContinueAnon: () => void }) {
  const { configured, signInWithGoogle } = useAuth();
  const [busy, setBusy] = useState(false);

  const google = async () => {
    if (busy) return;
    setBusy(true);
    try {
      // On success `onIdTokenChanged` in the AuthProvider flips `user`, which
      // dismisses this gate from the page. On failure we stay put to retry.
      await signInWithGoogle();
    } catch {
      /* popup closed / network — leave the screen up so the user can retry */
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ob-page">
      <div className="ob-card">
        <div className="ob-brand">
          <Sparkle size={18} fill="var(--accent)" color="var(--accent)" />
          <span className="brand-name">DietTrace</span>
        </div>
        <div className="ob-eyebrow">Welcome</div>
        <h1 className="ob-title">
          Know what you eat,
          <br />
          held to the gram.
        </h1>
        <p className="ob-sub">
          Sign in to keep your food log across devices — or jump straight in and
          use DietTrace anonymously. You can always sign in later from the
          account menu.
        </p>
        <div className="ob-actions">
          {configured && (
            <button
              type="button"
              className="si-google"
              onClick={google}
              disabled={busy}
            >
              <GoogleMark />
              Continue with Google
            </button>
          )}
          <button
            type="button"
            className="ob-btn-secondary"
            onClick={onContinueAnon}
          >
            Continue without an account
          </button>
        </div>
        <p className="si-fine">No email, no spam — your log stays on this device unless you sign in.</p>
      </div>
    </div>
  );
}
