"use client";

// The DietTrace day view. Through this is the shell + header + the
// day-macros band + the inline log input: a centered single-column page that
// owns the selected day, renders the ✦ DietTrace header, shows calories +
// P/C/F vs targets, and logs meals into today's list. The richer meal rows and
// agent's-work trace land in –9.7.
import { useEffect, useState } from "react";
import { Header } from "@/components/header";
import { DayMacros } from "@/components/day-macros";
import { LogInput } from "@/components/log-input";
import {
  getAnalysis,
  getGoals,
  type GoalProgress,
  type LogResponse,
} from "@/lib/api";
import { shiftDate } from "@/lib/date";

// A just-logged meal dropped into today's list. The full meal row (time, macro
// breakdown, confidence chip, expand) is built in 9.6; for now a row carries
// the text the user typed plus the response the agent returned.
interface LoggedMeal {
  text: string;
  result: LogResponse;
}

const ENERGY = "208";

export default function Home() {
  const [date, setDate] = useState(() => new Date());
  const [goals, setGoals] = useState<GoalProgress[]>([]);
  const [meals, setMeals] = useState<LoggedMeal[]>([]);

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
          onLogged={(text, result) =>
            setMeals((current) => [{ text, result }, ...current])
          }
        />
        <ul className="meals">
          {meals.map((meal, i) => {
            const kcal = meal.result.totals.find((n) => n.code === ENERGY)?.amount;
            return (
              <li className="meal" key={`${meal.result.id}-${i}`}>
                <span className="meal-text">{meal.text}</span>
                {kcal != null && (
                  <span className="meal-kcal mono tnum">{Math.round(kcal)} kcal</span>
                )}
              </li>
            );
          })}
        </ul>
      </main>
    </div>
  );
}
