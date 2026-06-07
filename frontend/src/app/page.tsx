"use client";

// The DietTrace day view: a centered single-column page that owns the selected
// day, renders the ✦ DietTrace header, the day-macros band (calories + P/C/F vs
// targets), the inline log input, and the day's logged meals as compact rows
// read from /history. Expanding a row reveals that
// meal's agent's-work trace, kept from its /log response.
import { useCallback, useEffect, useState } from "react";
import { Header } from "@/components/header";
import { DatePicker } from "@/components/date-picker";
import { DayMacros } from "@/components/day-macros";
import { LogInput } from "@/components/log-input";
import { LiveMeal, type LiveEntry } from "@/components/live-meal";
import { MealList, type MealDetail } from "@/components/meal-list";
import { SafetyNotice } from "@/components/safety-notice";
import type { AgentEvent } from "@/components/agent-decision";
import { Dashboard, type LatestTrace } from "@/components/dashboard";
import { OverviewModal } from "@/components/observability-modal";
import { MacroModal } from "@/components/macro-modal";
import { Onboarding } from "@/components/onboarding";
import {
  deleteMeal,
  getAnalysis,
  getGoals,
  getHistory,
  getProfile,
  logMealStream,
  type GoalProgress,
  type Meal,
  type Safety,
} from "@/lib/api";
import { clearOnboarded, isOnboardedFlag, markOnboarded } from "@/lib/onboarding";
import { clearSetup } from "@/lib/setup";
import { fromISODate, isSameDay, shiftDate, toISODate } from "@/lib/date";

export default function Home() {
  const [date, setDate] = useState(() => new Date());
  const [goals, setGoals] = useState<GoalProgress[]>([]);
  const [meals, setMeals] = useState<Meal[]>([]);
  // The agent's-work detail per meal id, captured from each /log response so an
  // expanded row can show the trace + per-item table the backend just produced.
  const [details, setDetails] = useState<Record<number, MealDetail>>({});
  // The in-progress meal while its /log/stream is running, or null when idle.
  const [live, setLive] = useState<LiveEntry | null>(null);
  // The supervisor's per-meal decisions, newest first (the agent-observability feed).
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);
  // Bumped whenever a correction/confirmation/seed happens, so the always-visible
  // learning panel in the Observability column refetches and stays in sync (the
  // corrections persist across day navigation instead of disappearing).
  const [reloadSignal, setReloadSignal] = useState(0);
  const bumpLearning = useCallback(() => setReloadSignal((n) => n + 1), []);
  // The safety guardrail result from the most recent log, or null when clear —
  // surfaces a calm supportive notice above the meals.
  const [safety, setSafety] = useState<Safety | null>(null);
  // Whether the combined Accuracy+Trust "Overview" page is open.
  const [overviewOpen, setOverviewOpen] = useState(false);
  // Whether the macro editor ("Set your targets") modal is open.
  const [macroOpen, setMacroOpen] = useState(false);
  // First-run gate: null while we decide, false → show onboarding, true → the app.
  // A returning browser (flag set) skips straight through; otherwise a user who
  // already has a saved profile or logged meals (a seeded judge, a returning
  // signed-in user) is treated as onboarded so they never re-see the welcome.
  const [onboarded, setOnboarded] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    // Decide off-render (async) so we never setState synchronously in the effect:
    // the localStorage flag is the fast path; otherwise a saved profile or any
    // logged meal also counts as onboarded (seeded judge / returning user).
    const decide = async (): Promise<boolean> => {
      if (isOnboardedFlag()) return true;
      const [profile, history] = await Promise.allSettled([
        getProfile(),
        getHistory(toISODate(new Date())),
      ]);
      const hasProfile =
        profile.status === "fulfilled" &&
        profile.value.profile_text.trim() !== "";
      const hasMeals =
        history.status === "fulfilled" && history.value.meals.length > 0;
      if (hasProfile || hasMeals) {
        markOnboarded();
        return true;
      }
      return false;
    };
    decide().then((v) => {
      if (!cancelled) setOnboarded(v);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load the daily targets first so the band isn't empty; fail-soft.
  useEffect(() => {
    getGoals()
      .then((res) =>
        setGoals((current) =>
          current.length
            ? current
            : res.goals.map((g) => ({ ...g, consumed: 0, remaining: g.target })),
        ),
      )
      .catch(() => {});
  }, []);

  // The meal list AND the day-macros band are both sourced for the selected day,
  // and re-fetch on date navigation and after a meal is logged or removed — so
  // navigating days updates both the meals and the consumed/remaining totals.
  const loadHistory = useCallback(() => {
    getHistory(toISODate(date))
      .then((res) => {
        setMeals(res.meals);
        // Rebuild the per-meal breakdown from the persisted fields so the table +
        // trace survive a reload / navigation; don't clobber richer session detail.
        setDetails((current) => {
          const next = { ...current };
          for (const m of res.meals) {
            if (!m.per_item) continue;
            // Refresh from the persisted fields every load so a corrected meal's
            // table + confidence update in place. Keep a richer in-session trace
            // when history's reconstructed one is empty (older logs).
            const prev = next[m.id];
            next[m.id] = {
              trace: m.trace && m.trace.length ? m.trace : (prev?.trace ?? []),
              perItem: m.per_item,
              confidence: m.confidence,
              reasons: m.reasons,
              axes: m.axes,
              needsReview: m.needs_review,
              reviewReason: m.review_reason ?? null,
            };
          }
          return next;
        });
      })
      .catch(() => {});
  }, [date]);

  const loadAnalysis = useCallback(() => {
    getAnalysis(toISODate(date))
      .then((res) => setGoals(res.goals))
      .catch(() => {});
  }, [date]);

  useEffect(() => {
    loadHistory();
    loadAnalysis();
  }, [loadHistory, loadAnalysis]);

  // Remove a logged meal: drop it optimistically, then reconcile both reads.
  const handleDelete = useCallback(
    (meal: Meal) => {
      setMeals((current) => current.filter((m) => m.id !== meal.id));
      deleteMeal(meal.id)
        .then(() => {
          loadHistory();
          loadAnalysis();
        })
        .catch(() => {});
    },
    [loadHistory, loadAnalysis],
  );

  // Stream a new meal: show the working entry immediately, append each agent
  // step as it streams in, then settle it into the list when the result lands.
  const handleSubmit = useCallback(
    (text: string) => {
      const day = toISODate(date);
      setLive({ text, steps: [] });
      setSafety(null);
      logMealStream(text, day, (event) => {
        if (event.type === "step") {
          setLive((current) =>
            current ? { ...current, steps: [...current.steps, event] } : current,
          );
          return;
        }
        // A safety-flagged input is not a meal: show the supportive notice and
        // log nothing (no row, no totals).
        if (event.safety?.flagged) {
          setSafety(event.safety);
          setLive(null);
          return;
        }
        const id = event.id ?? 0;
        const meal: Meal = {
          id,
          created_at: new Date().toISOString(),
          date: day,
          text,
          totals: event.totals ?? [],
        };
        setMeals((current) => [meal, ...current.filter((m) => m.id !== id)]);
        setDetails((current) => ({
          ...current,
          [id]: {
            trace: event.trace ?? [],
            perItem: event.per_item ?? [],
            confidence: event.confidence,
            reasons: event.reasons,
            axes: event.axes,
            needsReview: event.needs_review,
            reviewReason: event.review_reason,
          },
        }));
        setSafety(event.safety ?? null);
        if (event.supervisor) {
          const decided = event.supervisor;
          setAgentEvents((cur) =>
            [{ ...decided, id, mealText: text }, ...cur].slice(0, 30),
          );
        }
        setLive(null);
        loadHistory();
        loadAnalysis();
      }).catch(() => setLive(null));
    },
    [date, loadHistory, loadAnalysis],
  );

  const handleCorrected = useCallback(() => {
    bumpLearning();
    loadHistory();
    loadAnalysis();
  }, [bumpLearning, loadHistory, loadAnalysis]);

  // Onboarding finished (or was skipped): enter the app and refresh the day so
  // the just-saved targets show in the band.
  const handleOnboarded = useCallback(() => {
    setOnboarded(true);
    loadHistory();
    loadAnalysis();
    bumpLearning();
  }, [loadHistory, loadAnalysis, bumpLearning]);

  // Hold the paint until the gate decides (avoids flashing the app then the
  // welcome). A returning user resolves synchronously from the localStorage flag.
  if (onboarded === null) return <div className="ob-page" aria-busy="true" />;
  if (onboarded === false) return <Onboarding onDone={handleOnboarded} />;

  const heading = isSameDay(date, new Date()) ? "Today" : "Logged";

  // The latest agent trace to surface on the dashboard — the most recent meal
  // logged this session (historical rows carry no captured trace).
  const latestMeal = meals[0];
  const latestTrace: LatestTrace | null =
    latestMeal && details[latestMeal.id]?.trace?.length
      ? { text: latestMeal.text, steps: details[latestMeal.id].trace }
      : null;

  return (
    <div className="page">
      <main className="wrap wrap-wide">
        <Header
          date={date}
          onOpenOverview={() => setOverviewOpen(true)}
          onOpenMacros={() => setMacroOpen(true)}
          onSeeded={() => {
            loadHistory();
            loadAnalysis();
            bumpLearning();
          }}
          onViewDay={(iso) => setDate(fromISODate(iso))}
          onReset={() => {
            // Reset wipes the user server-side AND re-triggers onboarding, so a
            // clean slate always starts from the welcome flow (new-user parity).
            clearOnboarded();
            clearSetup();
            setOnboarded(false);
          }}
          onAuthChange={() => {
            loadHistory();
            loadAnalysis();
            bumpLearning();
          }}
        />
        <div className="layout">
          <div className="col-log">
            {/* The day card — date navigator + calorie/macro rings, one panel. */}
            <section className="day-card">
              <DatePicker
                date={date}
                onShift={(days) => setDate((d) => shiftDate(d, days))}
                onPickDate={setDate}
              />
              <DayMacros goals={goals} />
            </section>

            {/* The log card — input + the day's meals, a separate panel below. */}
            <section className="log-card">
              <h2 className="log-card-head">Food Log</h2>
              <LogInput onSubmit={handleSubmit} busy={live !== null} />
              <SafetyNotice safety={safety ?? undefined} />
              {live && <LiveMeal entry={live} />}
              <MealList
                meals={meals}
                heading={heading}
                detailsById={details}
                onEdit={handleDelete}
                onCorrected={handleCorrected}
              />
            </section>
          </div>
          <Dashboard
            reloadSignal={reloadSignal}
            latestTrace={latestTrace}
            agentEvents={agentEvents}
          />
        </div>
      </main>
      {overviewOpen && <OverviewModal onClose={() => setOverviewOpen(false)} />}
      {macroOpen && (
        <MacroModal
          onClose={() => setMacroOpen(false)}
          onSaved={() => {
            // Saved targets become the user's per-user goals; refresh the band.
            loadAnalysis();
          }}
        />
      )}
    </div>
  );
}
