import type { Spending, SpendingState, TopQuestion, UsageDay, UsageGroup, UsageSummary } from "../api/usage";
import { getMockBudgetSettings } from "./sampleSettings";

// Usage fixtures (mock only) matching the Calm usage design and the P05.9
// shapes. The populated demo month mirrors October: $41.20 spent of a $150
// monthly credit. Real aggregation is P05.9; the mock never invents costs.
const QUESTIONS_PER_DAY: number[] = [
  0.84, 1.22, 0.65, 0.31, 1.48, 1.62, 1.35, 1.1, 1.71, 0.52, 0.28, 1.56, 1.83, 1.44, 1.29,
  2.1, 0.66, 0.37, 1.52, 1.95, 1.38, 1.27, 1.66, 0.72, 0.41, 1.19, 0.97,
];
const LEARNING_PER_DAY: number[] = QUESTIONS_PER_DAY.map((_, i) => (i === 2 ? 7.2 : i === 19 ? 2.6 : 0));

const GROUP_COSTS: [string, number][] = [
  ["Planning and judging", 11.1],
  ["Learning", 9.8],
  ["Data helpers", 8.4],
  ["Writing answers", 5.6],
  ["Reviewing answers", 3.9],
  ["Document search", 2.4],
];

const TOP_QUESTIONS: TopQuestion[] = [
  { message_id: 4, chat_id: 3, question: "Why did delivery drop in Austin?", asked_at: "2025-10-26T10:00:00Z", seconds: 372, steps: 41, cost_usd: 3.84 },
  { message_id: 6, chat_id: 8, question: "Dallas vs Houston, last quarter", asked_at: "2025-10-22T10:00:00Z", seconds: 245, steps: 33, cost_usd: 2.96 },
  { message_id: 8, chat_id: 5, question: "Coupon impact in September", asked_at: "2025-10-19T10:00:00Z", seconds: 198, steps: 27, cost_usd: 2.61 },
  { message_id: 10, chat_id: 7, question: "Best hours to add staff", asked_at: "2025-10-21T10:00:00Z", seconds: 160, steps: 22, cost_usd: 2.18 },
  { message_id: 2, chat_id: 1, question: "How are we doing this month?", asked_at: "2025-10-27T10:00:00Z", seconds: 38, steps: 14, cost_usd: 1.92 },
];

const DEMO_MONTH = "2025-10";

function monthStorage(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

// The budget lives in the shared settings store now (P03.13); usage reads it
// from there so the Usage dialog and Settings save the same values.
export type { BudgetStore } from "./sampleSettings";
export { getMockBudgetSettings, updateMockBudgetSettings } from "./sampleSettings";

const SPENDING_KEY = "charie-mock-spending";

interface SpendingOverride {
  spent_usd?: number;
}

// Test-only override for the spent total (the design's warn/paused states).
export function setMockSpending(override: SpendingOverride): void {
  try {
    monthStorage()?.setItem(SPENDING_KEY, JSON.stringify(override));
  } catch {
    // Test-only state; ignore.
  }
}

function overrideSpent(): number | null {
  try {
    const raw = monthStorage()?.getItem(SPENDING_KEY);
    if (!raw) return null;
    const n = Number((JSON.parse(raw) as SpendingOverride).spent_usd);
    return Number.isFinite(n) && n >= 0 ? Math.round(n * 10000) / 10000 : null;
  } catch {
    return null;
  }
}

export function resetMockUsage(): void {
  try {
    monthStorage()?.removeItem("charie-mock-settings");
    monthStorage()?.removeItem("charie-mock-budget-settings");
    monthStorage()?.removeItem(SPENDING_KEY);
  } catch {
    // Nothing to clear.
  }
}

function daysInMonth(month: string): number {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

function monthLabel(month: string): string {
  const names = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return names[Number(month.slice(5, 7)) - 1];
}

function nextMonth(month: string): string {
  const [y, m] = month.split("-").map(Number);
  const next = new Date(Date.UTC(y, m, 1));
  return `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

export function mockSpending(fixtureSpent: number): Spending {
  const { spend_limit_usd, spend_warn_percent } = getMockBudgetSettings();
  const spent = overrideSpent() ?? fixtureSpent;
  const percent = spend_limit_usd > 0 ? (spent / spend_limit_usd) * 100 : 0;
  const state: SpendingState =
    percent >= 100 ? "paused" : percent >= spend_warn_percent ? "warn" : "ok";
  return {
    state,
    spent_usd: spent,
    limit_usd: spend_limit_usd,
    warn_percent: spend_warn_percent,
    percent_used: Math.round(percent * 100) / 100,
  };
}

// The mock usage summary for a month. The demo month (and, for a stable
// default screen, the real current month) is populated from fixtures;
// every other valid month is a zero-spend month.
export function mockUsage(month: string): UsageSummary {
  const days = daysInMonth(month);
  const label = monthLabel(month);
  const populated = month === DEMO_MONTH || month === currentMonth();
  const dayCount = populated ? Math.min(QUESTIONS_PER_DAY.length, days) : days;
  const perDay: UsageDay[] = Array.from({ length: populated ? dayCount : days }, (_, i) => ({
    date: `${i + 1} ${label}`,
    questions_usd: populated ? (QUESTIONS_PER_DAY[i] ?? 0) : 0,
    learning_usd: populated ? (LEARNING_PER_DAY[i] ?? 0) : 0,
    tests_usd: 0,
  }));
  const fixtureSpent =
    QUESTIONS_PER_DAY.slice(0, dayCount).reduce((a, b) => a + b, 0) +
    LEARNING_PER_DAY.slice(0, dayCount).reduce((a, b) => a + b, 0);
  const spent = populated ? Math.round(fixtureSpent * 100) / 100 : 0;
  const withSpent = mockSpending(spent);
  const daysSoFar = populated ? dayCount : 0;
  const expected =
    populated && daysSoFar > 0 ? Math.round(((spent / daysSoFar) * days * 100)) / 100 : spent;
  const groups: UsageGroup[] = populated
    ? GROUP_COSTS.map(([group, cost_usd]) => ({
        group,
        cost_usd,
        percent: spent > 0 ? Math.round((cost_usd / spent) * 1000) / 10 : 0,
      }))
    : [];
  return {
    month,
    days_in_month: days,
    resets_on: nextMonth(month),
    spent_usd: withSpent.spent_usd,
    limit_usd: withSpent.limit_usd,
    warn_percent: withSpent.warn_percent,
    percent_used: withSpent.percent_used,
    state: withSpent.state,
    expected_usd: expected,
    questions: {
      count: populated ? 24 : 0,
      cost_usd: populated ? Math.round((spent - 9.8) * 100) / 100 : 0,
    },
    learning_runs: { count: populated ? 2 : 0, cost_usd: populated ? 9.8 : 0 },
    per_day: perDay,
    per_group: groups,
    top_questions: populated ? TOP_QUESTIONS : [],
  };
}

export function currentMonth(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function isUsageMonth(value: string): boolean {
  const match = /^(\d{4})-(\d{2})$/.exec(value);
  if (!match) return false;
  const month = Number(match[2]);
  return month >= 1 && month <= 12;
}

// Share the populated fixture for the status snapshot.
export { DEMO_MONTH };
