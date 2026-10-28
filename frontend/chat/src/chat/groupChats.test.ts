import { describe, expect, test } from "vitest";
import { groupChats } from "./groupChats";
import type { ChatSummary } from "@charie/shared";

function chat(id: number, updatedAt: string): ChatSummary {
  return { id, title: `Chat ${id}`, created_at: updatedAt, updated_at: updatedAt };
}

// 2025-10-26T12:00:00Z is a Sunday noon UTC.
const NOON = Date.parse("2025-10-26T12:00:00Z");

describe("groupChats", () => {
  test("places each boundary date in exactly one group", () => {
    const chats = [
      chat(1, "2025-10-26T00:00:00Z"), // today (same calendar day UTC)
      chat(2, "2025-10-26T23:59:59Z"), // today, later the same day
      chat(3, "2025-10-25T00:00:01Z"), // yesterday
      chat(4, "2025-10-25T23:59:59Z"), // yesterday, just after midnight
      chat(5, "2025-10-24T12:00:00Z"), // previous 7 days (2 days ago)
      chat(6, "2025-10-19T12:00:00Z"), // previous 7 days (7 days ago, boundary)
      chat(7, "2025-10-18T12:00:00Z"), // older (8 days ago)
    ];
    const groups = groupChats(chats, NOON, "UTC");
    expect(groups.map((g) => g.label)).toEqual([
      "Today",
      "Yesterday",
      "Previous 7 days",
      "Older",
    ]);
    const byId = new Map(groups.flatMap((g) => g.chats.map((c) => [c.id, g.label])));
    expect(byId.get(1)).toBe("Today");
    expect(byId.get(2)).toBe("Today");
    expect(byId.get(3)).toBe("Yesterday");
    expect(byId.get(4)).toBe("Yesterday");
    expect(byId.get(5)).toBe("Previous 7 days");
    expect(byId.get(6)).toBe("Previous 7 days");
    expect(byId.get(7)).toBe("Older");
    // Every chat appears exactly once.
    expect([...byId.keys()].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  test("keeps input order within a group", () => {
    const groups = groupChats([chat(9, "2025-10-26T10:00:00Z"), chat(3, "2025-10-26T11:00:00Z")], NOON, "UTC");
    expect(groups).toHaveLength(1);
    expect(groups[0].chats.map((c) => c.id)).toEqual([9, 3]);
  });

  test("skips empty groups", () => {
    const groups = groupChats([chat(1, "2025-10-26T10:00:00Z")], NOON, "UTC");
    expect(groups.map((g) => g.label)).toEqual(["Today"]);
  });

  test("groups by the selected time zone, not UTC", () => {
    // 2025-10-26T03:30:00Z is still 25 Oct in New York (EDT, UTC-4).
    const chats = [chat(1, "2025-10-26T03:30:00Z")];
    expect(groupChats(chats, NOON, "UTC").map((g) => g.label)).toEqual(["Today"]);
    expect(groupChats(chats, NOON, "America/New_York").map((g) => g.label)).toEqual([
      "Yesterday",
    ]);
  });

  test("future and invalid dates land in Today", () => {
    const groups = groupChats(
      [chat(1, "2025-10-27T12:00:00Z"), { ...chat(2, "not-a-date"), updated_at: "not-a-date" }],
      NOON,
      "UTC",
    );
    expect(groups.map((g) => g.label)).toEqual(["Today"]);
    expect(groups[0].chats).toHaveLength(2);
  });
});
