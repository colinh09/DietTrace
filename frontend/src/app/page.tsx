"use client";

// The DietTrace day view. For this is the shell + header only: a
// centered single-column page that owns the selected day and renders the
// ✦ DietTrace header with its date navigation. The macros band, log input,
// and meal list land in –9.7.
import { useState } from "react";
import { Header } from "@/components/header";
import { shiftDate } from "@/lib/date";

export default function Home() {
  const [date, setDate] = useState(() => new Date());

  return (
    <div className="page">
      <main className="wrap">
        <Header
          date={date}
          onShift={(days) => setDate((d) => shiftDate(d, days))}
          onPickDate={setDate}
        />
      </main>
    </div>
  );
}
