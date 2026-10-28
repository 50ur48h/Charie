import type { ChatSummary } from "../api/types";

const NOW = Date.now();

function daysAgo(days: number): string {
  return new Date(NOW - days * 86_400_000).toISOString();
}

function chat(id: number, title: string, ageInDays: number): ChatSummary {
  const at = daysAgo(ageInDays);
  return { id, title, created_at: at, updated_at: at };
}

// The 8 titles from docs/designs/shared/sample-data.js, newest first.
// Chats 1-2 are from today, 3-4 from yesterday, the rest from two, three,
// four and six days ago, so P03.9's date groups come out as in the design.
const chats: ChatSummary[] = [
  chat(1, "How are we doing this month?", 0),
  chat(2, "Top dishes by profit", 0),
  chat(3, "Why did delivery drop in Austin?", 1),
  chat(4, "Weekend vs weekday sales", 1),
  chat(5, "Coupon impact in September", 2),
  chat(6, "Food waste by restaurant", 3),
  chat(7, "Best hours to add staff", 4),
  chat(8, "Dallas vs Houston, last quarter", 6),
];

export default chats;
