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
import {
  deleteMeal,
  getAnalysis,
  getGoals,
  getHistory,
  logMealStream,
  type GoalProgress,
  type Meal,
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
      .then((res) => setMeals(res.meals))
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
      logMealStream(text, day, (event) => {
        if (event.type === "step") {
          setLive((current) =>
            current ? { ...current, steps: [...current.steps, event] } : current,
          );
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
          [id]: { trace: event.trace ?? [], perItem: event.per_item ?? [] },
        }));
        setLive(null);
        loadHistory();
        loadAnalysis();
      }).catch(() => setLive(null));
    },
    [date, loadHistory, loadAnalysis],
  );

  const heading = isSameDay(date, new Date()) ? "Today" : "Logged";

  return (
    <div className="page">
      <main className="wrap">
        <Header
          date={date}
          onShift={(days) => setDate((d) => shiftDate(d, days))}
          onPickDate={setDate}
        />
        <DayMacros goals={goals} />
        <LogInput onSubmit={handleSubmit} busy={live !== null} />
        {live && <LiveMeal entry={live} />}
        <MealList
          meals={meals}
          heading={heading}
          detailsById={details}
          onEdit={handleDelete}
        />
      </main>
    </div>
  );
}
