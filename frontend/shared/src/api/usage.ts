// Usage and spending (architecture 09 addresses, P05.9 exact shapes — these
// types win if the plans differ (C005)). Money arrives as JSON numbers
// rounded to 4 decimals; labels are formatted on screen, never recomputed.
export type SpendingState = "ok" | "warn" | "paused";

export interface Spending {
  state: SpendingState;
  spent_usd: number;
  limit_usd: number;
  warn_percent: number;
  percent_used: number;
}

export interface UsageTotals {
  count: number;
  cost_usd: number;
}

export interface UsageDay {
  date: string;
  questions_usd: number;
  learning_usd: number;
  tests_usd: number;
}

export interface UsageGroup {
  group: string;
  cost_usd: number;
  percent: number;
}

export interface TopQuestion {
  message_id: number;
  chat_id: number;
  question: string;
  asked_at: string;
  seconds: number;
  steps: number;
  cost_usd: number;
}

export interface UsageSummary {
  month: string;
  days_in_month: number;
  resets_on: string;
  spent_usd: number;
  limit_usd: number;
  warn_percent: number;
  percent_used: number;
  state: SpendingState;
  expected_usd: number;
  questions: UsageTotals;
  learning_runs: UsageTotals;
  per_day: UsageDay[];
  per_group: UsageGroup[];
  top_questions: TopQuestion[];
}

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

// GET /api/usage?month=YYYY-MM (architecture 09, P05.9 shapes). No month
// means the current month; a bad month is a 400 with a plain message.
export function useUsage(month?: string) {
  return useQuery({
    queryKey: ["usage", month ?? "current"],
    queryFn: ({ signal }) =>
      apiFetch<UsageSummary>(month ? `/api/usage?month=${month}` : "/api/usage", { signal }),
    retry: false,
  });
}
