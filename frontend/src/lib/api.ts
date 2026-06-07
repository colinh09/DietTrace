// Typed client for the DietTrace FastAPI backend.
//
// One call per endpoint the frontend needs — log a meal, read a day's history,
// the aggregate analysis, and the daily goals. The response types mirror the
// shapes returned by `dietrace.web.app` so callers stay type-safe end to end.
// The base URL comes from NEXT_PUBLIC_API_BASE (set per deploy) and falls back
// to the local dev server.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";

// A single nutrient amount, keyed by its USDA number code (e.g. "208" energy).
// Matches `dietrace.nutrition.models.Nutrient`.
export interface Nutrient {
  code: string;
  name: string;
  amount: number;
  unit: string;
}

// Daily macro/calorie target from `GET /goals` (`dietrace.web.goals`).
export interface Goal {
  code: string;
  name: string;
  target: number;
  unit: string;
}

// A goal with the day's consumed/remaining figures, as `/analysis` returns it.
export interface GoalProgress extends Goal {
  consumed: number;
  remaining: number;
}

// One logged food's portion and its scaled nutrient panel (`LoggedItem`).
// `portion_basis` explains how the gram weight was derived — e.g. "matched
// serving: 1 cup" — so the UI can show why each food got its gram value
//. Absent on older stored meals.
export interface LoggedItem {
  fdc_id: number;
  description: string;
  grams: number;
  portion_basis?: string;
  nutrients: Nutrient[];
}

// One step of the agent's reconstructed work, surfaced behind a meal's expand.
// Every step carries `step` + `summary`; the rest depends on the step kind.
// `basis` on an `estimate_portion` step explains which serving or measure was
// used.
export interface TraceStep {
  step:
    | "recall"
    | "parse_meal"
    | "search_nutrition"
    | "web_search"
    | "estimate_portion"
    | "log_entry";
  summary: string;
  food?: string;
  matched?: string;
  fdc_id?: number;
  grams?: number;
  basis?: string;
  foods?: (string | null)[];
  totals?: Nutrient[];
}

// The rule-based safety guardrail result for a logged input.
// `flagged` is true when the text matched a supportive-care concern; `category`
// names it and `message` is the calm notice to surface (empty when clear).
export interface Safety {
  flagged: boolean;
  category: string | null;
  message: string;
}

// One confidence axis from the online quality eval. Each of the
// four deterministic sub-scores — resolution completeness, source quality,
// portion sanity, calorie plausibility — is reported with its 0–1 score and
// a short ✓/⚠ note so the UI can render a full per-axis breakdown, not just
// the failing reasons.
export interface ConfidenceAxis {
  name: string;
  score: number;
  note: string;
}

// `POST /log` — the logged meal plus the agent's-work trace. `confidence`
// (0–1) and `reasons` come from the online quality eval.
export interface LogResponse {
  id: number;
  per_item: LoggedItem[];
  totals: Nutrient[];
  trace: TraceStep[];
  confidence: number;
  reasons: string[];
  // All four confidence sub-scores with ✓/⚠ notes.
  axes?: ConfidenceAxis[];
  // Set when confidence < 0.6: the backend asks the user to glance, carrying the
  // top reason. `review_reason` is null when nothing to show.
  needs_review: boolean;
  review_reason: string | null;
  // The rule-based safety guardrail result.
  safety: Safety;
  // The supervisor's per-meal decision: one of bank_feedback | add_dataset_point
  // | retune, with a one-line reason (agent-observability).
  supervisor?: SupervisorDecision;
}

// One per-meal supervisor decision (what the autonomous supervisor chose to do).
export interface SupervisorDecision {
  op: "bank_feedback" | "add_dataset_point" | "retune";
  reason: string;
}

// A persisted meal as stored by `dietrace.web.store.MealLogStore`. The breakdown
// fields (per_item, trace, the quality eval) are persisted with the meal so the
// per-item table survives a reload or navigating away and back.
export interface Meal {
  id: number;
  created_at: string;
  date: string;
  text: string;
  totals: Nutrient[];
  per_item?: LoggedItem[];
  trace?: TraceStep[];
  confidence?: number;
  reasons?: string[];
  axes?: ConfidenceAxis[];
  needs_review?: boolean;
  review_reason?: string | null;
  // True for a held-out confirmed meal mirrored as a visible row (a "dataset
  // point") — ground truth the gate scores against, not an agent estimate.
  dataset_point?: boolean;
}

// `GET /history?date=` — one calendar day's meals (default: today).
export interface HistoryResponse {
  date: string;
  meals: Meal[];
}

// `GET /goals` — the daily targets.
export interface GoalsResponse {
  goals: Goal[];
}

// `GET /analysis` — the day's aggregate totals and per-goal progress.
export interface AnalysisResponse {
  meal_count: number;
  totals: Nutrient[];
  goals: GoalProgress[];
  traces_buffered: number;
}

// A stable anonymous id per browser — there's no login, so this is how the
// backend scopes a person's meals + corrections (the per-user memory layer).
// Minted once and kept in localStorage; the same id rides every request.
export function userId(): string {
  if (typeof window === "undefined") return "anon";
  let id = window.localStorage.getItem("diettrace_uid");
  if (!id) {
    id =
      window.crypto?.randomUUID?.() ??
      `u-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    window.localStorage.setItem("diettrace_uid", id);
  }
  return id;
}

// The current Firebase ID token for a signed-in user, kept in sync by the auth
// layer (onIdTokenChanged → setAuthToken). Null when signed out / not configured,
// in which case requests fall back to the anonymous X-DietTrace-User id.
let _idToken: string | null = null;

export function setAuthToken(token: string | null): void {
  _idToken = token;
}

// Headers every request carries: JSON, the anonymous user id (fallback), and —
// when signed in — the Firebase ID token the backend verifies into a stable uid.
function authHeaders(extra?: HeadersInit): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-DietTrace-User": userId(),
    ...(extra as Record<string, string>),
  };
  if (_idToken) headers["Authorization"] = `Bearer ${_idToken}`;
  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: authHeaders(init?.headers),
  });
  if (!response.ok) {
    throw new Error(`DietTrace API ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

// Log a meal in natural language; returns its totals, per-item panel, and trace.
// `date` (YYYY-MM-DD, the viewed day) files the meal under the client's local day.
export async function logMeal(text: string, date?: string): Promise<LogResponse> {
  return request<LogResponse>("/log", {
    method: "POST",
    body: JSON.stringify({ text, date }),
  });
}

// Delete a logged meal by id.
export async function deleteMeal(id: number): Promise<void> {
  await request(`/meals/${id}`, { method: "DELETE" });
}

// One kept item of a corrected meal sent to POST /correct (removed items are
// simply omitted). The backend rescales the panel from original to corrected grams.
export interface CorrectionItemInput {
  description: string;
  fdc_id: number;
  original_grams: number;
  corrected_grams: number;
  nutrients: Nutrient[];
}

// The result of correcting a meal — it's now remembered (cache + few-shot) and
// pushed to Arize as ground truth.
export interface CorrectionResult {
  ok: boolean;
  added_to_arize: boolean;
  corrections: number;
  per_item: LoggedItem[];
  totals: Nutrient[];
  phoenix_url: string;
}

// Save a corrected meal: remove wrong items / fix portions → the agent remembers
// it (recalls the same meal, learns from similar ones) and Arize gets the truth.
// Pass mealId to also rewrite the stored meal's totals in-place.
export async function correctMeal(
  mealText: string,
  items: CorrectionItemInput[],
  mealId?: number,
): Promise<CorrectionResult> {
  return request<CorrectionResult>("/correct", {
    method: "POST",
    body: JSON.stringify({ meal_text: mealText, items, meal_id: mealId ?? null }),
  });
}

// How many corrections this user has taught the agent.
export async function getMemory(): Promise<{ corrections: number }> {
  return request<{ corrections: number }>("/memory");
}

// Read one day's logged meals. Omit `date` for today (the backend default).
export async function getHistory(date?: string): Promise<HistoryResponse> {
  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  return request<HistoryResponse>(`/history${query}`);
}

// Read the day's aggregate analysis (totals consumed + per-goal remaining) for
// `date` (default today on the backend), so it tracks date navigation.
export async function getAnalysis(date?: string): Promise<AnalysisResponse> {
  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  return request<AnalysisResponse>(`/analysis${query}`);
}

// Read the daily macro/calorie goals.
export async function getGoals(): Promise<GoalsResponse> {
  return request<GoalsResponse>("/goals");
}

// One scored accuracy dimension, baseline vs current (0–1, higher is better).
export interface AccuracyMetric {
  key: string;
  label: string;
  baseline: number;
  current: number;
}

// `GET /accuracy` — the Arize accuracy story + measured improvement.
export interface AccuracyReport {
  headline: {
    calorie_accuracy: number;
    macro_accuracy: number;
    within_tolerance: number;
  };
  metrics: AccuracyMetric[];
  loop: { step: string; label: string }[];
  dataset: { cases: number; source: string };
  phoenix_url: string;
  // "live" when read from Phoenix experiments, "measured" on fallback.
  source: "live" | "measured";
  // Number of Phoenix experiments behind the numbers (null on fallback).
  experiments: number | null;
  // Each experiment's scores (oldest → newest) — the accuracy trend over time.
  trend: { calorie: number; macro: number; within_tolerance: number; portion: number }[];
  // Macro-plan evaluator surface.
  macros: {
    headline: { pass_rate: number; mean_score: number };
    experiments: number | null;
    trend: { pass_rate: number; mean_score: number }[];
    dataset: { cases: number };
  };
}

// Read the accuracy / Arize-observability report.
export async function getAccuracy(): Promise<AccuracyReport> {
  return request<AccuracyReport>("/accuracy");
}

// One recent low-confidence meal the dashboard asks the user to revisit.
export interface TrustRecentLog {
  text: string;
  confidence: number;
  review_reason: string | null;
  created_at: string;
}

// `GET /trust` — rolling trust stats for the calling user:
// how many meals logged, the mean confidence, the fraction flagged for review,
// where the numbers came from, and the recent meals worth a second look.
export interface TrustReport {
  count: number;
  mean_confidence: number;
  needs_review_pct: number;
  source_breakdown: Record<string, number>;
  recent_low_confidence: TrustRecentLog[];
}

// Read the user's trust report (powers the /trust dashboard).
export async function getTrust(): Promise<TrustReport> {
  return request<TrustReport>("/trust");
}

// One portion correction the user has taught the agent: a food and the grams
// they fixed, before → after.
export interface RecentCorrection {
  food: string;
  original_grams: number;
  corrected_grams: number;
  created_at: string;
}

// `GET /feedback/recent` — the user's recent corrections for the
// "what you've taught" panel, newest first.
export interface RecentFeedbackResponse {
  corrections: RecentCorrection[];
}

// Read the user's recent corrections (powers the "what you've taught" panel).
export async function getRecentFeedback(): Promise<RecentFeedbackResponse> {
  return request<RecentFeedbackResponse>("/feedback/recent");
}

// Input for POST /feedback/freeform — the user's natural-language comment about a
// logged meal, plus the current per_item context so the backend can apply the
// structured interpretation without a second DB read.
export interface FreeformFeedbackInput {
  meal_id: number | null;
  meal_text: string;
  feedback_text: string;
  current_items: LoggedItem[];
}

// What DietTrace learned from the free-form feedback (14.12): the structured
// interpretation (kind / target_food / adjustment / rationale) plus the updated
// per_item + totals so the UI can refresh without a history reload.
export interface FreeformFeedbackResult {
  ok: boolean;
  applied: boolean;
  kind: string | null;
  target_food: string;
  adjustment: number | null;
  // Absolute gram target for an absolute portion fix ("about 30 grams"); null
  // when the user gave a relative amount ("half") expressed via `adjustment`.
  target_grams?: number | null;
  rationale: string;
  scope: string;
  stored_as_preference: boolean;
  per_item: LoggedItem[];
  totals: Nutrient[];
  // The recomputed online eval after the fix (null for standing-rule feedback).
  confidence?: number | null;
  axes?: ConfidenceAxis[] | null;
  reasons?: string[] | null;
  needs_review?: boolean | null;
  review_reason?: string | null;
  added_to_arize: boolean;
  corrections?: number;
  phoenix_url: string;
  error?: string;
}

// Submit free-form feedback for a logged meal; returns the structured adaptation
// so the UI can immediately show "DietTrace learned: …".
export async function submitFreeformFeedback(
  input: FreeformFeedbackInput,
): Promise<FreeformFeedbackResult> {
  return request<FreeformFeedbackResult>("/feedback/freeform", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// A single Server-Sent Event from `POST /log/stream`: a `step` as the agent
// works, or the final `result` (which also persists the meal and carries its id).
export interface StreamEvent {
  type: "step" | "result";
  step?:
    | "recall"
    | "parse_meal"
    | "search_nutrition"
    | "web_search"
    | "estimate_portion"
    | "log_entry";
  status?: "running" | "done";
  summary?: string;
  food?: string;
  matched?: string;
  fdc_id?: number;
  grams?: number;
  foods?: string[];
  totals?: Nutrient[];
  per_item?: LoggedItem[];
  trace?: TraceStep[];
  id?: number;
  // On the final `result` event: the online quality eval.
  confidence?: number;
  reasons?: string[];
  axes?: ConfidenceAxis[];
  // The low-confidence review flag + its top reason.
  needs_review?: boolean;
  review_reason?: string | null;
  // The rule-based safety guardrail result.
  safety?: Safety;
  // On the final `result` event: the supervisor's per-meal decision.
  supervisor?: SupervisorDecision;
}

// Stream a meal log: `onEvent` fires for each step as the agent works, then once
// more with the final `result`. Resolves when the stream ends.
export async function logMealStream(
  text: string,
  date: string | undefined,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/log/stream`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ text, date }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`DietTrace /log/stream failed: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf("\n\n");
    while (sep >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (frame.startsWith("data: ")) {
        onEvent(JSON.parse(frame.slice(6)) as StreamEvent);
      }
      sep = buffer.indexOf("\n\n");
    }
  }
}

// ── Macros: AI-assisted planning + per-user targets ───────────────────────
// The nutritionist's macro side. `/macros/plan` computes a plan (deterministic
// calories + a clamped/guarded AI split, scored by an online eval, biased toward
// the user's saved preference); `/macros/save` persists the (possibly edited)
// targets and remembers the split; `/macros/retune` reports the alignment lift.

// Daily targets keyed by USDA code: "208" kcal · "203" protein · "205" carb · "204" fat.
export type MacroTargets = Record<string, number>;

export type MacroSex = "male" | "female";
export type MacroActivity =
  | "sedentary"
  | "light"
  | "moderate"
  | "active"
  | "very_active";
export type MacroGoal = "cut" | "maintain" | "bulk";

// POST /macros/plan body — EITHER a preset key (no-profile path) OR a full profile.
export interface MacroPlanRequest {
  preset?: string | null;
  age?: number;
  sex?: MacroSex;
  height_cm?: number;
  weight_kg?: number;
  activity?: MacroActivity;
  goal?: MacroGoal;
  preference?: string | null;
  ai_help?: boolean;
}

// The macro-plan online eval verdict (deterministic consistency + safety check).
export interface MacroEval {
  score: number;
  pass: boolean;
  consistency: { score: number; flag?: string; reason?: string };
  safety: { score: number; flags?: string[]; reasons?: string[] };
  flags: string[];
  reasons: string[];
}

// How closely the served split matches the user's saved preference (Phase 2).
export interface MacroAdherence {
  score: number;
  protein_delta: number;
  fat_delta: number;
}

// POST /macros/plan response — the plan plus its accountability surface.
export interface MacroPlan {
  targets: MacroTargets;
  rationale: string;
  source: "formula" | "ai" | "preset";
  steps: Record<string, unknown>[];
  clamped: string[];
  eval: MacroEval | null;
  // True when the split was biased toward the user's remembered preference.
  personalized: boolean;
  adherence: MacroAdherence | null;
}

// Compute a macro plan (does NOT persist). Pass a profile or `{ preset }`.
export async function postMacrosPlan(body: MacroPlanRequest): Promise<MacroPlan> {
  return request<MacroPlan>("/macros/plan", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// The result of saving targets: the agent now remembers this user's split.
export interface MacroSaveResult {
  ok: boolean;
  user: string;
  targets: MacroTargets;
  // True when the preference was banked to Arize Phoenix as ground truth.
  banked: boolean;
}

// Persist the (possibly edited) targets for the calling user.
export async function postMacrosSave(
  targets: MacroTargets,
  rationale?: string | null,
  source?: string | null,
): Promise<MacroSaveResult> {
  return request<MacroSaveResult>("/macros/save", {
    method: "POST",
    body: JSON.stringify({ targets, rationale, source }),
  });
}

// POST /macros/retune — the alignment lift from the user's saved preference
// (generic-default plan → personalized plan), the "it adapts to you" signal.
export interface MacroRetune {
  cases: number;
  before: number | null;
  after: number | null;
  improved: boolean;
  protein_shift?: number;
}

export async function postMacrosRetune(body: MacroPlanRequest): Promise<MacroRetune> {
  return request<MacroRetune>("/macros/retune", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// The persona a demo seed loaded — what was logged, the seeded learning state,
// and the on-screen under-count, so the explainer modal can describe it exactly.
export interface SeededPersona {
  key: string;
  label: string;
  blurb: string;
  goal_rationale: string;
  hook_meal: string;
  hook_note: string;
  learns: string;
  meal_texts: string[];
  confirmation_texts: string[];
  correction_texts: string[];
}

// `POST /demo/seed` — populate the calling user's account with a persona's
// visible day (filed on the PREVIOUS day so today stays clean) + the learning
// seed, so a judge can see the full app state immediately.
export interface SeedDemoResult {
  seeded: boolean;
  meals: number;
  // The day the visible playground meals landed on (today, ISO).
  meal_date: string;
  // The day the confirmed dataset-point rows landed on (yesterday, ISO).
  dataset_date: string;
  goals_set: boolean;
  confirmations: number;
  corrections: number;
  persona: SeededPersona;
}

// The selectable demo personas (the persona loader). Keys match the backend.
export const DEMO_PERSONAS = [
  {
    key: "runner",
    label: "Endurance runner",
    blurb: "Under-logs her training carbs.",
  },
  {
    key: "bodybuilder",
    label: "Bodybuilder",
    blurb: "Under-logs his post-lift protein.",
  },
] as const;

export async function seedDemo(
  date?: string,
  persona?: string,
): Promise<SeedDemoResult> {
  return request<SeedDemoResult>("/demo/seed", {
    method: "POST",
    body: JSON.stringify({ date, persona }),
  });
}

// `POST /session/reset` — wipe the calling user's meals, goals, and everything
// DietTrace has learned about them back to a clean slate.
export interface SessionResetResult {
  reset: boolean;
  cleared: Record<string, number>;
}

export async function resetSession(): Promise<SessionResetResult> {
  return request<SessionResetResult>("/session/reset", { method: "POST" });
}

// ── Learning loop ──────────────────────────────────

// One generalized rule the corrector wrote, with provenance back to the
// corrections that produced it.
export interface PreferenceRule {
  rule: string;
  rationale: string;
  from_feedback: number[];
}

// The per-user preference block — what DietTrace has learned about you.
export interface PreferenceBlock {
  block_text: string;
  version: number;
  updated_at: string;
  provenance: PreferenceRule[];
}

// One confirmed meal in the held-out gate set, with the calories it asserts.
export interface ConfirmedMeal {
  id: number;
  meal_text: string;
  calories: number;
}

export interface PreferencesResponse {
  block: PreferenceBlock | null;
  corrections: number;
  // New (unprocessed) corrections — the only ones the next retune folds in.
  new_corrections: number;
  confirmations: number;
  // The confirmed meals (Input A) the gate tests a proposed block against.
  confirmed: ConfirmedMeal[];
  min_corrections: number;
}

// One banked correction (Input B) — natural-language feedback + emphasis weight.
export interface FeedbackItem {
  id: number;
  created_at: string;
  feedback_text: string;
  meal_text: string | null;
  weight: number;
  // True once it's been folded into a shipped block (a retune won't re-learn it).
  processed: boolean;
}

export interface RetuneScores {
  usda: number;
  fit: number;
}

export interface RetuneVerdict {
  ship: boolean;
  usda_ok: boolean;
  fit_gain: boolean;
  reason: string;
  eps: number;
}

// The result of a gated retune: the proposal, both score sets, and the verdict.
export interface LearningRetuneResult {
  ok: boolean;
  shipped?: boolean;
  verdict?: RetuneVerdict;
  current?: RetuneScores;
  proposed?: RetuneScores;
  proposed_block?: string;
  rules?: PreferenceRule[];
  version?: number | null;
  fit_cases?: number;
  usda_cases?: number;
  // when ok=false: "not_enough_corrections" | "no_new_corrections" | "corrector_failed"
  reason?: string;
  have?: number;
  need?: number;
}

// `GET /preferences` — the learned block + the counts that gate a retune.
export async function getPreferences(): Promise<PreferencesResponse> {
  return request<PreferencesResponse>("/preferences");
}

// The user's freeform "goals + eating style" profile — standing context the
// corrector reads on every retune so personalization reflects who they are.
export async function getProfile(): Promise<{ profile_text: string }> {
  return request<{ profile_text: string }>("/profile");
}

export async function setProfile(
  profile_text: string,
): Promise<{ ok: boolean; profile_text: string }> {
  return request("/profile", {
    method: "POST",
    body: JSON.stringify({ profile_text }),
  });
}

// `POST /confirm` — "does this look right?": a confirmed meal becomes a held-out
// ground-truth datapoint (Input A) the gate scores against.
export async function confirmMeal(
  meal_text: string,
  items: LoggedItem[],
  totals: Nutrient[],
): Promise<{ ok: boolean; id: number; confirmations: number }> {
  return request("/confirm", {
    method: "POST",
    body: JSON.stringify({ meal_text, items, totals }),
  });
}

export async function listLearningFeedback(): Promise<{
  feedback: FeedbackItem[];
  count: number;
}> {
  return request("/learning/feedback");
}

export async function editLearningFeedback(
  id: number,
  body: { feedback_text?: string; weight?: number },
): Promise<{ ok: boolean }> {
  return request(`/learning/feedback/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteLearningFeedback(
  id: number,
): Promise<{ deleted: boolean }> {
  return request(`/learning/feedback/${id}`, { method: "DELETE" });
}

// `POST /learning/retune` — the gated retune: corrector proposes, the gate scores
// it on USDA + held-out fit, ships only if the rule passes. Runs live evals, so
// it can take a while.
export async function learningRetune(): Promise<LearningRetuneResult> {
  return request<LearningRetuneResult>("/learning/retune", { method: "POST" });
}

// One live event from `POST /learning/retune/stream` — the retune made visible:
// a `phase` boundary, the proposed `rule`, one `score` per meal as it's re-tested
// (before/after a 0–1 calorie-accuracy), and a final `done` carrying the verdict.
export type LearningRetuneEvent =
  | { type: "phase"; phase: "propose" | "fit" | "usda"; label: string; n?: number }
  | { type: "rule"; rules: PreferenceRule[] }
  // The full eval set up front, so the UI lists every meal before scoring starts.
  | { type: "manifest"; rows: { set: "fit" | "usda"; text: string }[] }
  | {
      type: "score";
      set: "fit" | "usda";
      i: number;
      n: number;
      text: string;
      expected: number;
      before: number;
      after: number;
    }
  | ({ type: "done" } & LearningRetuneResult);

// Stream the gated retune: `onEvent` fires per phase/rule/scored-meal as the eval
// runs, then once with the `done` verdict — so the retest is visible happening.
// `full` checks the entire USDA standard set (slower); the default quick tune
// checks a representative sample so it finishes fast.
export async function learningRetuneStream(
  onEvent: (event: LearningRetuneEvent) => void,
  full = false,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/learning/retune/stream${full ? "?full=1" : ""}`,
    { method: "POST", headers: authHeaders() },
  );
  if (!response.ok || !response.body) {
    throw new Error(`DietTrace /learning/retune/stream failed: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf("\n\n");
    while (sep >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (frame.startsWith("data: ")) {
        onEvent(JSON.parse(frame.slice(6)) as LearningRetuneEvent);
      }
      sep = buffer.indexOf("\n\n");
    }
  }
}

// ── Experiments ──────────────────────────────────────────────────────────
// The supervisor runs an eval experiment off the hot path (no run-experiment MCP
// tool exists), then reads the results back over Phoenix MCP. Kick + poll here.

export interface ExperimentRun {
  run_id: string;
  status: "running" | "done" | "error";
}

export interface ExperimentStatus {
  run_id: string;
  status: "running" | "done" | "error";
  summary?: Record<string, unknown> | null;
}

// Start an experiment run; returns a run id to poll with getExperimentStatus.
export async function runExperiment(
  dataset?: string,
  name?: string,
): Promise<ExperimentRun> {
  return request<ExperimentRun>("/experiments/run", {
    method: "POST",
    body: JSON.stringify({ dataset, name }),
  });
}

// Poll an experiment run's status (running | done | error) + its summary.
export async function getExperimentStatus(
  runId: string,
): Promise<ExperimentStatus> {
  return request<ExperimentStatus>(`/experiments/${encodeURIComponent(runId)}`);
}
