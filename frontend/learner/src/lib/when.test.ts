import { describe, expect, test } from "vitest";
import { clockTime, dayOrDate, howLong, shortDate, timeAgo } from "./when";

// Fixed instant, so the timeAgo gaps below are exact in every timezone.
// The shortDate inputs are built in local time instead: a fixed-offset
// midnight changes date across timezones (CI in UTC saw "25 Oct").
// Noon avoids daylight-saving edges.
const NOW = new Date("2025-10-27T21:30:00+05:30");

describe("when", () => {
  test("shortDate adds the year only for other years", () => {
    expect(shortDate(new Date(2025, 9, 26, 12).toISOString(), NOW)).toBe("26 Oct");
    expect(shortDate(new Date(2024, 9, 26, 12).toISOString(), NOW)).toBe("26 Oct 2024");
  });

  test("timeAgo says 2 hours ago", () => {
    expect(timeAgo("2025-10-27T21:29:30+05:30", NOW)).toBe("just now");
    expect(timeAgo("2025-10-27T21:29:00+05:30", NOW)).toBe("1 minute ago");
    expect(timeAgo("2025-10-27T21:00:00+05:30", NOW)).toBe("30 minutes ago");
    expect(timeAgo("2025-10-27T19:30:00+05:30", NOW)).toBe("2 hours ago");
    expect(timeAgo("2025-10-26T21:30:00+05:30", NOW)).toBe("yesterday");
    expect(timeAgo("2025-10-20T21:30:00+05:30", NOW)).toBe("7 days ago");
  });

  test("dayOrDate says Today and Yesterday", () => {
    const now = new Date(2026, 9, 27, 12);
    expect(dayOrDate(new Date(2026, 9, 27, 9).toISOString(), now)).toBe("Today");
    expect(dayOrDate(new Date(2026, 9, 26, 23, 59).toISOString(), now)).toBe("Yesterday");
    expect(dayOrDate(new Date(2026, 9, 20, 12).toISOString(), now)).toBe("20 Oct");
    expect(dayOrDate(new Date(2025, 9, 20, 12).toISOString(), now)).toBe("20 Oct 2025");
  });

  test("clockTime says 9:12 pm", () => {
    expect(clockTime(new Date(2026, 9, 27, 21, 12).toISOString())).toBe("9:12 pm");
    expect(clockTime(new Date(2026, 9, 27, 2, 5).toISOString())).toBe("2:05 am");
    expect(clockTime(new Date(2026, 9, 27, 12, 0).toISOString())).toBe("12:00 pm");
  });

  test("howLong says 4 min and 1 h 48 min", () => {
    const start = new Date(2026, 9, 26, 2, 0).toISOString();
    expect(howLong(start, new Date(2026, 9, 26, 2, 4).toISOString())).toBe("4 min");
    expect(howLong(start, new Date(2026, 9, 26, 3, 48).toISOString())).toBe("1 h 48 min");
  });
});
