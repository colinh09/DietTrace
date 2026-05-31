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
import { MealList, type MealDetail } from "@/components/meal-list";
import {
  getAnalysis,
  getGoals,
  getHistory,
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

  // /goals gives the targets immediately so the band isn't empty; /analysis
  // then layers the day's consumed/remaining on top. Each is fail-soft — a
  // missing backend just leaves the band at its targets (or empty). /analysis
  // is not date-aware yet (it aggregates the current day), so this loads once
  // on mount rather than re-firing on date navigation.
  useEffect(() => {
    let cancelled = false;
    getGoals()
      .then((res) => {
        if (cancelled) return;
        setGoals((current) =>
          current.length
            ? current
            : res.goals.map((g) => ({ ...g, consumed: 0, remaining: g.target })),
        );
      })
      .catch(() => {});
    getAnalysis()
      .then((res) => {
        if (!cancelled) setGoals(res.goals);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  // The meal list is sourced from /history for the selected day; re-fetches on
  // date navigation and again after a meal is logged. Fail-soft: a missing
  // backend just leaves the list empty.
  const loadHistory = useCallback(() => {
    getHistory(toISODate(date))
      .then((res) => setMeals(res.meals))
      .catch(() => {});
  }, [date]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

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
        <LogInput
          onLogged={(_text, result) => {
            setDetails((current) => ({
              ...current,
              [result.id]: { trace: result.trace, perItem: result.per_item },
            }));
            loadHistory();
          }}
        />
        <MealList meals={meals} heading={heading} detailsById={details} />
      </main>
    </div>
  );
}
