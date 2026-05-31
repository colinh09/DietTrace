import { describe, expect, it } from "vitest";
import { formatHeaderDate, isSameDay, shiftDate, toISODate } from "@/lib/date";

describe("date helpers", () => {
  // May 30, 2026 is a Saturday — the day shown in the v2 design.
  const may30 = new Date(2026, 4, 30);

  it("formats a header label as weekday, month day", () => {
    expect(formatHeaderDate(may30)).toBe("Sat, May 30");
  });

  it("shifts forward and back by whole days without mutating the input", () => {
    expect(toISODate(shiftDate(may30, 1))).toBe("2026-05-31");
    expect(toISODate(shiftDate(may30, -1))).toBe("2026-05-29");
    // crossing a month boundary
    expect(toISODate(shiftDate(may30, 2))).toBe("2026-06-01");
    expect(toISODate(may30)).toBe("2026-05-30");
  });

  it("renders an ISO date in local time (not UTC-shifted)", () => {
    expect(toISODate(may30)).toBe("2026-05-30");
  });

  it("compares two dates by calendar day", () => {
    expect(isSameDay(may30, new Date(2026, 4, 30, 23, 59))).toBe(true);
    expect(isSameDay(may30, new Date(2026, 4, 31))).toBe(false);
  });
});
