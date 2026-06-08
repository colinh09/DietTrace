"use client";

// The day navigator — ‹ prev · date · next › plus a calendar affordance that
// drops a month-grid popover. Lives in the day-summary card (not the navbar), so
// the date sits right next to the calories it scopes (MacroFactor-style).
import { useEffect, useRef, useState } from "react";
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
} from "lucide-react";
import { formatHeaderDate, isSameDay } from "@/lib/date";
import { ResetDialog } from "@/components/reset-dialog";

const DOW = ["S", "M", "T", "W", "T", "F", "S"];

// Month-grid popover. Browses months independently of the selected `date`.
function CalendarPopover({ date, onPick }: { date: Date; onPick: (d: Date) => void }) {
  const [view, setView] = useState(new Date(date.getFullYear(), date.getMonth(), 1));
  const today = new Date();
  const year = view.getFullYear();
  const month = view.getMonth();
  const firstDow = new Date(year, month, 1).getDay();
  const dayCount = new Date(year, month + 1, 0).getDate();

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDow; i += 1) cells.push(null);
  for (let d = 1; d <= dayCount; d += 1) cells.push(d);

  return (
    <div className="cal-pop">
      <div className="cal-head">
        <button
          type="button"
          className="cal-nav"
          onClick={() => setView(new Date(year, month - 1, 1))}
          aria-label="previous month"
        >
          ‹
        </button>
        <span className="cal-month">
          {view.toLocaleDateString("en-US", { month: "long", year: "numeric" })}
        </span>
        <button
          type="button"
          className="cal-nav"
          onClick={() => setView(new Date(year, month + 1, 1))}
          aria-label="next month"
        >
          ›
        </button>
      </div>
      <div className="cal-grid cal-dow" aria-hidden="true">
        {DOW.map((d, i) => (
          <span key={i} className="cal-dow-c">
            {d}
          </span>
        ))}
      </div>
      <div className="cal-grid" role="grid">
        {cells.map((d, i) =>
          d == null ? (
            <span key={i} />
          ) : (
            <button
              key={i}
              type="button"
              className={
                "cal-day" +
                (isSameDay(new Date(year, month, d), date) ? " sel" : "") +
                (isSameDay(new Date(year, month, d), today) ? " today" : "")
              }
              onClick={() => onPick(new Date(year, month, d))}
            >
              {d}
            </button>
          ),
        )}
      </div>
    </div>
  );
}

export function DatePicker({
  date,
  onShift,
  onPickDate,
  onReset,
}: {
  date: Date;
  onShift: (days: number) => void;
  onPickDate: (date: Date) => void;
  // Opens the Reset confirmation — the quiet second entry point on the date row
  // (the account menu is the first). Absent → no Reset control here.
  onReset?: () => void;
}) {
  const [resetOpen, setResetOpen] = useState(false);
  const [calOpen, setCalOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!calOpen) return;
    const handle = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setCalOpen(false);
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [calOpen]);

  return (
    <div className="datenav" ref={ref}>
      <button
        type="button"
        className="date-arrow"
        onClick={() => onShift(-1)}
        aria-label="previous day"
      >
        <ChevronLeft size={18} />
      </button>
      <button
        type="button"
        className="date-label mono"
        onClick={() => setCalOpen((o) => !o)}
      >
        {formatHeaderDate(date)}
      </button>
      <button
        type="button"
        className="date-arrow"
        onClick={() => onShift(1)}
        aria-label="next day"
      >
        <ChevronRight size={18} />
      </button>
      <button
        type="button"
        className={"date-cal" + (calOpen ? " on" : "")}
        onClick={() => setCalOpen((o) => !o)}
        aria-label="open calendar"
      >
        <CalendarIcon size={16} />
      </button>
      {calOpen && (
        <CalendarPopover
          date={date}
          onPick={(d) => {
            onPickDate(d);
            setCalOpen(false);
          }}
        />
      )}
      {onReset && (
        <button
          type="button"
          className="datenav-reset"
          onClick={() => setResetOpen(true)}
        >
          <RotateCcw size={13} aria-hidden="true" /> Reset
        </button>
      )}
      {resetOpen && onReset && (
        <ResetDialog onClose={() => setResetOpen(false)} onReset={onReset} />
      )}
    </div>
  );
}
