// Firebase app + auth, initialized from NEXT_PUBLIC_FIREBASE_* env vars.
//
// Graceful by design: if the config isn't set (local dev without Firebase, or a
// deploy that hasn't wired it yet), `auth` is null and the app stays in
// anonymous-only mode — no sign-in UI, everything else works unchanged. Set the
// env vars (Firebase console → Project settings → Web app) to light up Google
// sign-in.
import { type FirebaseApp, getApps, initializeApp } from "firebase/app";
import { type Auth, getAuth } from "firebase/auth";

const config = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// Minimum needed to talk to Firebase Auth.
export const isAuthConfigured = Boolean(config.apiKey && config.projectId);

let app: FirebaseApp | null = null;
let authInstance: Auth | null = null;

if (isAuthConfigured) {
  app = getApps()[0] ?? initializeApp(config as Record<string, string>);
  authInstance = getAuth(app);
}

export const auth = authInstance;
