"use client";

// The DietTrace day view. Through this is the shell + header + the
// day-macros band: a centered single-column page that owns the selected day,
// renders the ✦ DietTrace header, and shows calories + P/C/F vs targets. The
// log input and meal list land in –9.7.
import { useEffect, useState } from "react";
import { Header } from "@/components/header";
import { DayMacros } from "@/components/day-macros";
import { getAnalysis, getGoals, type GoalProgress } from "@/lib/api";
import { shiftDate } from "@/lib/date";

export default function Home() {
  const [date, setDate] = useState(() => new Date());
  const [goals, setGoals] = useState<GoalProgress[]>([]);

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
      </main>
    </div>
  );
}
