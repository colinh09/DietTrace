// A small client-side snapshot of what the user chose during onboarding, so the
// "Set your targets" screen and the "Persona details" screen can reflect it —
// WITHOUT storing body details on the server (the backend keeps targets only,
// never the profile inputs; this snapshot lives in the browser).
//
//   • "own"     — the body answers the user typed (only the ones they gave) plus
//                 their freeform lifestyle text.
//   • "persona" — a seeded demo: the persona's made-up stats + the seed result
//                 (for the persona-details explainer).
import type {
  MacroActivity,
  MacroGoal,
  MacroSex,
  SeedDemoResult,
} from "@/lib/api";

export interface ProfileInputs {
  age?: number;
  sex?: MacroSex;
  height_cm?: number;
  weight_kg?: number;
  activity?: MacroActivity;
  goal?: MacroGoal;
  preference?: string;
}

export interface OwnSetup {
  kind: "own";
  inputs: ProfileInputs;
  lifestyle: string;
}
export interface PersonaSetup {
  kind: "persona";
  personaKey: string;
  inputs: ProfileInputs;
  result: SeedDemoResult;
}
export type Setup = OwnSetup | PersonaSetup;

const KEY = "diettrace_setup";

export function getSetup(): Setup | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Setup) : null;
  } catch {
    return null;
  }
}

export function setSetup(s: Setup): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    // storage full / disabled — non-fatal, the screens just fall back to blanks
  }
}

export function clearSetup(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEY);
}

// Made-up body stats for each demo persona — used only to prefill the macro
// screen and the persona-details view. The persona's ACTUAL seeded targets come
// from the backend (DEMO_GOALS); these are a plausible body behind that story.
export const PERSONA_INPUTS: Record<string, ProfileInputs> = {
  runner: {
    age: 29,
    sex: "female",
    height_cm: 168,
    weight_kg: 57,
    activity: "very_active",
    goal: "maintain",
    preference: "carb-load before long runs, high protein to recover",
  },
  bodybuilder: {
    age: 27,
    sex: "male",
    height_cm: 181,
    weight_kg: 92,
    activity: "active",
    goal: "bulk",
    preference: "keep protein very high for muscle gain",
  },
  // Archived personas — kept here (commented out) so they can be restored
  // alongside the backend ARCHIVED_PERSONAS:
  // everyday: {
  //   age: 38,
  //   sex: "male",
  //   height_cm: 178,
  //   weight_kg: 84,
  //   activity: "light",
  //   goal: "cut",
  //   preference: "eats out a few times a week; trying to lose a little weight",
  // },
  // creator: {
  //   age: 28,
  //   sex: "male",
  //   height_cm: 178,
  //   weight_kg: 79,
  //   activity: "very_active",
  //   goal: "cut",
  //   preference:
  //     "lifts in the morning, walks a lot; small deficit with carbs high enough for training",
  // },
};
