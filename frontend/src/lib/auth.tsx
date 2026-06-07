"use client";

// Auth context: wraps the app, tracks the signed-in user, and keeps the API
// layer's bearer token in sync. When Firebase isn't configured it's inert —
// `configured` is false, `user` stays null, and the app runs anonymous-only.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  GoogleAuthProvider,
  onIdTokenChanged,
  signInWithPopup,
  signOut as fbSignOut,
  type User,
} from "firebase/auth";
import { auth, isAuthConfigured } from "@/lib/firebase";
import { setAuthToken } from "@/lib/api";

interface AuthState {
  // The signed-in user, or null (anonymous / signed out / not configured).
  user: User | null;
  // False until the initial auth state resolves (avoids a sign-in flicker).
  loading: boolean;
  // Whether Firebase Auth is wired at all (drives whether to show sign-in UI).
  configured: boolean;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(isAuthConfigured);

  useEffect(() => {
    // When Firebase isn't configured `loading` already initialized to false
    // (isAuthConfigured), so there's nothing to do and nothing to set here.
    if (!auth) return;
    // Fires on sign-in/out AND on token refresh — keep the API bearer token fresh.
    const unsub = onIdTokenChanged(auth, async (u) => {
      setUser(u);
      setAuthToken(u ? await u.getIdToken() : null);
      setLoading(false);
    });
    return unsub;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    if (!auth) return;
    await signInWithPopup(auth, new GoogleAuthProvider());
  }, []);

  const signOut = useCallback(async () => {
    if (!auth) return;
    await fbSignOut(auth);
    setAuthToken(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      configured: isAuthConfigured,
      signInWithGoogle,
      signOut,
    }),
    [user, loading, signInWithGoogle, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    // Used outside the provider (or SSR) — behave as anonymous, never throw.
    return {
      user: null,
      loading: false,
      configured: false,
      signInWithGoogle: async () => {},
      signOut: async () => {},
    };
  }
  return ctx;
}
