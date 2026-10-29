import { describe, expect, test } from "vitest";
import { shortDate, timeAgo } from "./when";

const NOW = new Date("2025-10-27T21:30:00+05:30");

describe("when", () => {
  test("shortDate adds the year only for other years", () => {
    expect(shortDate("2025-10-26T00:00:00+05:30", NOW)).toBe("26 Oct");
    expect(shortDate("2024-10-26T00:00:00+05:30", NOW)).toBe("26 Oct 2024");
  });

  test("timeAgo says 2 hours ago", () => {
    expect(timeAgo("2025-10-27T21:29:30+05:30", NOW)).toBe("just now");
    expect(timeAgo("2025-10-27T21:29:00+05:30", NOW)).toBe("1 minute ago");
    expect(timeAgo("2025-10-27T21:00:00+05:30", NOW)).toBe("30 minutes ago");
    expect(timeAgo("2025-10-27T19:30:00+05:30", NOW)).toBe("2 hours ago");
    expect(timeAgo("2025-10-26T21:30:00+05:30", NOW)).toBe("yesterday");
    expect(timeAgo("2025-10-20T21:30:00+05:30", NOW)).toBe("7 days ago");
  });
});
