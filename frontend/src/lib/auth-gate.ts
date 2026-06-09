// Remembers that the user chose the anonymous path on the sign-in screen, so a
// reload drops them straight into the app instead of re-prompting. Signing in
// (Firebase `user` becomes set) or signing out is the source of truth otherwise;
// this only covers "continue without an account". SSR/locked-storage safe.
const ANON_KEY = "diettrace_anon_choice";

export function hasChosenAnon(): boolean {
  try {
    return window.localStorage.getItem(ANON_KEY) === "1";
  } catch {
    return false;
  }
}

export function chooseAnon(): void {
  try {
    window.localStorage.setItem(ANON_KEY, "1");
  } catch {
    /* private mode / storage disabled — the gate just re-asks next load */
  }
}

// Signing out of the anonymous session: forget the choice so the next load (or an
// immediate reload) drops back to the sign-in gate.
export function clearAnon(): void {
  try {
    window.localStorage.removeItem(ANON_KEY);
  } catch {
    /* storage disabled — nothing to clear */
  }
}
