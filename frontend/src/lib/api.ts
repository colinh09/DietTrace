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
export interface LoggedItem {
  fdc_id: number;
  description: string;
  grams: number;
  nutrients: Nutrient[];
}

// One step of the agent's reconstructed work, surfaced behind a meal's expand.
// Every step carries `step` + `summary`; the rest depends on the step kind.
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

// `POST /log` — the logged meal plus the agent's-work trace. `confidence`
// (0–1) and `reasons` come from the online quality eval.
export interface LogResponse {
  id: number;
  per_item: LoggedItem[];
  totals: Nutrient[];
  trace: TraceStep[];
  confidence: number;
  reasons: string[];
  // Set when confidence < 0.6: the backend asks the user to glance, carrying the
  // top reason. `review_reason` is null when nothing to show.
  needs_review: boolean;
  review_reason: string | null;
  // The rule-based safety guardrail result.
  safety: Safety;
}

// A persisted meal as stored by `dietrace.web.store.MealLogStore`.
export interface Meal {
  id: number;
  created_at: string;
  date: string;
  text: string;
  totals: Nutrient[];
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

// Headers every request carries: JSON + the caller's anonymous user id.
function authHeaders(extra?: HeadersInit): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-DietTrace-User": userId(),
    ...(extra as Record<string, string>),
  };
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
export async function correctMeal(
  mealText: string,
  items: CorrectionItemInput[],
): Promise<CorrectionResult> {
  return request<CorrectionResult>("/correct", {
    method: "POST",
    body: JSON.stringify({ meal_text: mealText, items }),
  });
}

// How many corrections this user has taught the agent.
export async function getMemory(): Promise<{ corrections: number }> {
  return request<{ corrections: number }>("/memory");
}

// The before/after of re-testing the agent on the user's own corrected meals.
export interface RetuneResult {
  cases: number;
  before: number | null;
  after: number | null;
  improved: boolean;
}

// Re-tune & re-test: run the agent on your corrected meals, base vs with-memory.
export async function retune(): Promise<RetuneResult> {
  return request<RetuneResult>("/retune", { method: "POST" });
}

// One corrected meal as it's scored during a streamed re-test.
export interface RetuneCase {
  type: "case";
  text: string;
  expected_calories: number;
  before: number;
  after: number;
}

// The final roll-up of a streamed re-test.
export interface RetuneSummary {
  type: "summary";
  cases: number;
  before: number | null;
  after: number | null;
  improved: boolean;
}

export type RetuneEvent = RetuneCase | RetuneSummary;

// Stream the re-test: `onEvent` fires per corrected meal as it's scored, then
// once with the summary — so the eval is visible happening in the UI.
export async function retuneStream(
  onEvent: (event: RetuneEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}/retune/stream`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!response.ok || !response.body) {
    throw new Error(`DietTrace /retune/stream failed: ${response.status}`);
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
        onEvent(JSON.parse(frame.slice(6)) as RetuneEvent);
      }
      sep = buffer.indexOf("\n\n");
    }
  }
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
  // The low-confidence review flag + its top reason.
  needs_review?: boolean;
  review_reason?: string | null;
  // The rule-based safety guardrail result.
  safety?: Safety;
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
