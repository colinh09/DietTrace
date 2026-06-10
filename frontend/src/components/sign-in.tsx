"use client";

// The dedicated sign-in screen — a full-page split (matches the design mock):
// LEFT = a sage "stage" holding the brand, the hero copy, and a live agent-step
// "trace" card (the product's observability made visible); RIGHT = the sign-in
// card. "Continue with Google" to keep a log across devices, or "Continue without
// an account" to use DietTrace anonymously. When Firebase isn't configured the
// Google option is hidden and the anonymous path is the only one.
import { useState } from "react";
import {
  Check,
  Lock,
  ScanLine,
  SlidersHorizontal,
  Utensils,
  type LucideIcon,
} from "lucide-react";
import { BrandMark } from "@/components/brand-mark";
import { useAuth } from "@/lib/auth";

// Google's "G" mark — inline so it needs no asset and inherits sizing.
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
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

// The "how it reads a meal" trace — the agent's steps as a connected dotted
// timeline, ending in an Arize Phoenix MCP score (the observability money shot).
interface TraceStepDef {
  Icon: LucideIcon;
  label: string;
  body?: string;
  quote?: boolean;
  phoenix?: boolean;
}

const TRACE_STEPS: TraceStepDef[] = [
  {
    Icon: Utensils,
    label: "Reads your meal",
    body: "“two eggs and avocado toast”",
    quote: true,
  },
  { Icon: ScanLine, label: "Matches USDA foods", body: "egg · avocado · sourdough" },
  {
    Icon: SlidersHorizontal,
    label: "Learns your portions",
    body: "your toast runs bigger — noted",
  },
  { Icon: Check, label: "Scored against Your Dataset", phoenix: true },
];

function LiveTrace() {
  return (
    <div className="lt">
      <div className="lt-head">
        <span className="lt-eyebrow mono">How it reads a meal</span>
        <span className="lt-live mono">
          <span className="lt-pulse" aria-hidden="true" />
          Live
        </span>
      </div>
      <div className="lt-trace">
        {TRACE_STEPS.map((s, i) => (
          <div className="lt-node" key={s.label}>
            <span
              className={"lt-dot" + (i === TRACE_STEPS.length - 1 ? " fill" : "")}
              aria-hidden="true"
            />
            <div className="lt-node-head">
              <s.Icon size={14} className="lt-node-icon" aria-hidden="true" />
              <span className="lt-node-key">{s.label}</span>
            </div>
            {s.body && (
              <div className={"lt-node-body" + (s.quote ? " quote" : "")}>
                {s.body}
              </div>
            )}
            {s.phoenix && (
              <span className="phoenix-tag">
                <span className="pdot" aria-hidden="true" />
                Arize Phoenix · MCP
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
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
    <div className="si-page">
      {/* LEFT — sage stage: brand, hero copy, and the live trace visual */}
      <div className="si-stage">
        <div className="si-grain" aria-hidden="true" />
        <div className="si-brand">
          <BrandMark size={32} />
          <span className="brand-name">DietTrace</span>
        </div>
        <div className="si-cols">
          <div className="si-textcol">
            <span className="si-eyebrow mono">Welcome</span>
            <h1 className="si-hero">Know what you eat, held to the gram.</h1>
            <p className="si-sub">
              An AI nutritionist — plain-English meals in, accurate macros out.
            </p>
          </div>
          <div className="si-viscol">
            <LiveTrace />
          </div>
        </div>
      </div>

      {/* RIGHT — the sign-in card */}
      <div className="si-right">
        <div className="si-card">
          <span className="si-card-eyebrow mono">Get started</span>
          <h2 className="si-card-h">Pick up where you left off</h2>
          <p className="si-card-sub">
            Sign in to keep your food log across devices — or jump straight in. You
            can always sign in later from the account menu.
          </p>

          <div className="si-actions">
            {configured && (
              <button
                type="button"
                className="si-btn si-btn-google"
                onClick={google}
                disabled={busy}
              >
                <GoogleMark />
                Continue with Google
              </button>
            )}
            <button
              type="button"
              className="si-btn si-btn-anon"
              onClick={onContinueAnon}
            >
              Continue without an account
            </button>
          </div>

          <div className="si-reassure">
            <Lock size={14} aria-hidden="true" />
            <span>
              No email, no spam — your log stays on this device unless you sign in.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
