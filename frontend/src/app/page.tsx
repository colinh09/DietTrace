"use client";

// The DietTrace day view: a centered single-column page that owns the selected
// day, renders the ✦ DietTrace header, the day-macros band (calories + P/C/F vs
// targets), the inline log input, and the day's logged meals as compact rows
// read from /history. Expanding a row reveals that
// meal's agent's-work trace, kept from its /log response.
import { useCallback, useEffect, useState } from "react";
import { Header } from "@/components/header";
import { DayMacros } from "@/components/day-macros";
import { LogInput } from "@/components/log-input";
import { LiveMeal, type LiveEntry } from "@/components/live-meal";
import { MealList, type MealDetail } from "@/components/meal-list";
import { SafetyNotice } from "@/components/safety-notice";
import { Dashboard, type LatestTrace } from "@/components/dashboard";
import { ObservabilityModal, type ObsTab } from "@/components/observability-modal";
import { MacroModal } from "@/components/macro-modal";
import {
  deleteMeal,
  getAnalysis,
  getGoals,
  getHistory,
  getMemory,
  getRecentFeedback,
  logMealStream,
  type GoalProgress,
  type Meal,
  type RecentCorrection,
  type Safety,
} from "@/lib/api";
import { isSameDay, shiftDate, toISODate } from "@/lib/date";

export default function Home() {
  const [date, setDate] = useState(() => new Date());
  const [goals, setGoals] = useState<GoalProgress[]>([]);
  const [meals, setMeals] = useState<Meal[]>([]);
  // The agent's-work detail per meal id, captured from each /log response so an
  // expanded row can show the trace + per-item table the backend just produced.
  const [details, setDetails] = useState<Record<number, MealDetail>>({});
  // The in-progress meal while its /log/stream is running, or null when idle.
  const [live, setLive] = useState<LiveEntry | null>(null);
  // How many corrections this user has taught — drives the re-tune panel.
  const [corrections, setCorrections] = useState(0);
  // The user's recent corrections — drives the "what you've taught" panel (12.8).
  const [taught, setTaught] = useState<RecentCorrection[]>([]);
  // The safety guardrail result from the most recent log, or null when clear —
  // surfaces a calm supportive notice above the meals.
  const [safety, setSafety] = useState<Safety | null>(null);
  // Which observability tab is open as a popup over the page (null = closed).
  const [obs, setObs] = useState<ObsTab | null>(null);
  // Whether the macro editor ("Set your targets") modal is open.
  const [macroOpen, setMacroOpen] = useState(false);

  const loadMemory = useCallback(() => {
    getMemory()
      .then((res) => setCorrections(res.corrections))
      .catch(() => {});
    getRecentFeedback()
      .then((res) => setTaught(res.corrections))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadMemory();
  }, [loadMemory]);

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
            if (m.per_item && next[m.id] == null) {
              next[m.id] = {
                trace: m.trace ?? [],
                perItem: m.per_item,
                confidence: m.confidence,
                reasons: m.reasons,
                axes: m.axes,
                needsReview: m.needs_review,
                reviewReason: m.review_reason ?? null,
              };
            }
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
        setLive(null);
        loadHistory();
        loadAnalysis();
      }).catch(() => setLive(null));
    },
    [date, loadHistory, loadAnalysis],
  );

  const handleCorrected = useCallback(() => {
    loadMemory();
    loadHistory();
    loadAnalysis();
  }, [loadMemory, loadHistory, loadAnalysis]);

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
          onShift={(days) => setDate((d) => shiftDate(d, days))}
          onPickDate={setDate}
          onOpenObs={setObs}
          onOpenMacros={() => setMacroOpen(true)}
          onSeeded={() => {
            loadHistory();
            loadAnalysis();
          }}
        />
        <div className="layout">
          <div className="col-log">
            <DayMacros goals={goals} />
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
          </div>
          <Dashboard
            corrections={corrections}
            taught={taught}
            latestTrace={latestTrace}
          />
        </div>
      </main>
      {obs && <ObservabilityModal initialTab={obs} onClose={() => setObs(null)} />}
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
