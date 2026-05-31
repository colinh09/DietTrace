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
  step: "parse_meal" | "search_nutrition" | "estimate_portion" | "log_entry";
  summary: string;
  food?: string;
  matched?: string;
  fdc_id?: number;
  grams?: number;
  foods?: (string | null)[];
  totals?: Nutrient[];
}

// `POST /log` — the logged meal plus the agent's-work trace.
export interface LogResponse {
  id: number;
  per_item: LoggedItem[];
  totals: Nutrient[];
  trace: TraceStep[];
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`DietTrace API ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

// Log a meal in natural language; returns its totals, per-item panel, and trace.
export async function logMeal(text: string): Promise<LogResponse> {
  return request<LogResponse>("/log", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

// Read one day's logged meals. Omit `date` for today (the backend default).
export async function getHistory(date?: string): Promise<HistoryResponse> {
  const query = date ? `?date=${encodeURIComponent(date)}` : "";
  return request<HistoryResponse>(`/history${query}`);
}

// Read the aggregate analysis: totals consumed and per-goal remaining.
export async function getAnalysis(): Promise<AnalysisResponse> {
  return request<AnalysisResponse>("/analysis");
}

// Read the daily macro/calorie goals.
export async function getGoals(): Promise<GoalsResponse> {
  return request<GoalsResponse>("/goals");
}
