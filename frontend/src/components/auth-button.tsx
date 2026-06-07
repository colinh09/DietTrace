"use client";

// Sign-in affordance for the header. Renders nothing when Firebase isn't
// configured (anonymous-only mode). Otherwise: a "Sign in" button when signed
// out, or the user's name + a sign-out control when signed in.
import { useState } from "react";
import { LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth";

export function AuthButton({ onAuthChange }: { onAuthChange?: () => void }) {
  const { user, loading, configured, signInWithGoogle, signOut } = useAuth();
  const [busy, setBusy] = useState(false);

  if (!configured || loading) return null;

  const run = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    try {
      await fn();
      onAuthChange?.();
    } catch {
      // Popup closed / network — leave state as-is, the user can retry.
    } finally {
      setBusy(false);
    }
  };

  if (!user) {
    return (
      <button
        type="button"
        className="nav-item auth-signin"
        onClick={() => run(signInWithGoogle)}
        disabled={busy}
      >
        Sign in
      </button>
    );
  }

  const name = user.displayName?.split(" ")[0] ?? user.email ?? "Account";
  return (
    <span className="auth-user">
      {user.photoURL ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="auth-avatar" src={user.photoURL} alt="" />
      ) : (
        <span className="auth-avatar auth-avatar-fallback" aria-hidden="true">
          {name.charAt(0).toUpperCase()}
        </span>
      )}
      <span className="auth-name">{name}</span>
      <button
        type="button"
        className="auth-signout"
        onClick={() => run(signOut)}
        disabled={busy}
        title="Sign out"
        aria-label="sign out"
      >
        <LogOut size={13} aria-hidden="true" />
      </button>
    </span>
  );
}
