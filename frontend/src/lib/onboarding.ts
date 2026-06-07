// Whether this browser has finished (or skipped) first-run onboarding.
//
// A returning visitor should never see the welcome/profile flow again, so the
// completion is a single localStorage flag. The page gate ALSO treats a user who
// already has a saved profile or logged meals as onboarded (a seeded judge, or a
// returning signed-in user on a fresh browser) — see page.tsx — so this flag is
// the fast path, not the only source of truth.

const KEY = "diettrace_onboarded";

export function isOnboardedFlag(): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(KEY) === "1";
}

export function markOnboarded(): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, "1");
}

export function clearOnboarded(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
}
