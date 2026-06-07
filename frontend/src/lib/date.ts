// Calendar-day helpers for the header's date navigation. Everything works in
// local time: a day is a wall-clock day, and `toISODate` is the key the API's
// `?date=YYYY-MM-DD` expects (see lib/api.ts).

// "Sat, May 30" — the label shown between the date arrows in the v2 design.
export function formatHeaderDate(date: Date): string {
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

// "8:14 AM" — a meal's logged time, from its ISO `created_at`, in local time.
// The store records `created_at` in UTC; the browser renders it wall-clock.
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

// A fresh Date `days` away from `date`; never mutates the input.
export function shiftDate(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

// YYYY-MM-DD in local time (not the UTC-shifted Date.toISOString()).
export function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

// Parse a "YYYY-MM-DD" key (from the API) into a local-time Date — the inverse
// of `toISODate`. Avoids `new Date(iso)`, which parses the string as UTC.
export function fromISODate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

// True when both dates fall on the same calendar day.
export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}
