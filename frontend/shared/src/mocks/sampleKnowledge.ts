import type { KnowledgeEntry } from "../knowledge/types";

// Sample knowledge entries (mock only), matching the Calm knowledge design.
// The design's ids differ from the stable fixture keys the plans require, so
// KEY_MAP translates them: metric.net_sales, metric.food_cost_percent,
// default.lunch and data_problem.late_orders keep their keys everywhere.
// Kinds and confidences use the real API codes; the evidence fields (how,
// sql, checks, quoted sources, string history) are design-mock only.
export const KEY_MAP: Record<string, string> = {
  "metric.net_sales": "net-sales",
  "metric.food_cost_percent": "food-cost",
  "default.lunch": "lunch",
  "data_problem.late_orders": "late-data",
};

export const KNOWLEDGE_VERSION = 14;

const entries: KnowledgeEntry[] = [
  {
    key: "metric.net_sales",
    kind: "metric",
    title: "Net sales",
    confidence: "confirmed",
    used: 32,
    meaning:
      'What the restaurants actually earned from food and drink. When someone just says "sales", this is what Charie uses.',
    updated_at: null,
    how: [
      "Start with the order total",
      "Take away tax, the delivery fee and any discount",
      "Only count completed orders",
      "Leave out test restaurants (9000-9099)",
    ],
    sql: "SUM(o.total - o.tax - o.delivery_fee - o.discount)\nWHERE o.status = 'completed' AND r.is_test = false",
    checks: [
      "Runs without errors",
      "Results make sense: no negative sales",
      "Matches the finance report: Q3 = $3.91M",
      "Restaurants add up to the company total",
    ],
    sources: [
      {
        doc: 'Finance wiki, "Net sales"',
        quote: "Net sales is the order value after discounts, before tax.",
      },
    ],
    history: ['12 Oct - You chose "including delivery fees"', "3 Oct - First learned from the Finance wiki"],
  },
  {
    key: "metric.avg_order",
    kind: "metric",
    title: "Average order",
    confidence: "checked",
    used: 18,
    updated_at: null,
    meaning: "Net sales divided by the number of completed orders. Never an average of averages.",
  },
  {
    key: "metric.food_cost_percent",
    kind: "metric",
    title: "Food cost %",
    confidence: "from_document",
    used: 6,
    updated_at: null,
    meaning: "Ingredient cost as a share of net sales. Target is 28-31%.",
  },
  {
    key: "metric.labor_cost_percent",
    kind: "metric",
    title: "Labor cost %",
    confidence: "guessed",
    used: 2,
    updated_at: null,
    meaning: "Staff cost as a share of net sales. The formula isn't confirmed yet.",
  },
  {
    key: "default.sales_word",
    kind: "default",
    title: '"Sales"',
    confidence: "conflicting",
    used: 41,
    updated_at: null,
    meaning: "Two documents disagree about delivery fees. There's a question waiting for you.",
  },
  {
    key: "default.last_week",
    kind: "default",
    title: '"Last week"',
    confidence: "confirmed",
    used: 14,
    updated_at: null,
    meaning: "The last full week, Monday to Sunday.",
  },
  {
    key: "default.lunch",
    kind: "default",
    title: '"Lunch"',
    confidence: "from_document",
    used: 5,
    updated_at: null,
    meaning: "Orders placed between 11 am and 3 pm.",
  },
  {
    key: "data.orders_total",
    kind: "column",
    title: "orders.total",
    confidence: "checked",
    used: 29,
    updated_at: null,
    meaning: "The full order amount in US dollars, including tax and the delivery fee.",
  },
  {
    key: "data.order_items",
    kind: "table",
    title: "order_items",
    confidence: "checked",
    used: 11,
    updated_at: null,
    meaning: "One row per dish in an order. Never add up order totals after joining this table.",
  },
  {
    key: "rule.test_stores",
    kind: "rule",
    title: "Leave out test restaurants",
    confidence: "guessed",
    used: 41,
    updated_at: null,
    meaning: "Restaurants 9000-9099 look like tests. There's a question waiting for you.",
  },
  {
    key: "rule.usd_only",
    kind: "rule",
    title: "Money is always in US dollars",
    confidence: "confirmed",
    used: 41,
    updated_at: null,
    meaning: "From your notes: never convert currencies.",
  },
  {
    key: "default.coupon_codes",
    kind: "code",
    title: "Coupon codes like MEGA0926",
    confidence: "guessed",
    used: 3,
    updated_at: null,
    meaning: "The last 4 digits look like month and year. There's a question waiting for you.",
  },
  {
    key: "event.austin_outage",
    kind: "event",
    title: "Delivery app outage, Austin",
    confidence: "from_document",
    used: 2,
    updated_at: null,
    meaning: "14 Oct 6:20 pm to 16 Oct 9:05 pm. From the incident log.",
  },
  {
    key: "data_problem.late_orders",
    kind: "data_problem",
    title: "Late orders from 3 restaurants",
    confidence: "checked",
    used: 1,
    updated_at: null,
    meaning: "On 20 Oct, orders from 3 restaurants arrived a day late.",
  },
];

export function keyToEntryKey(key: string): string {
  return KEY_MAP[key] ?? key;
}

function matches(entry: KnowledgeEntry, query: string): boolean {
  const hay = `${entry.key} ${entry.title} ${entry.meaning ?? ""}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter((word) => word.length > 0)
    .every((word) => hay.includes(word));
}

// Newest first is the caller's job; this keeps kind and search in one place
// for the published list and the learner's draft and published copies.
// Kinds are the real API codes; groups are filtered on the screen.
export function filterKnowledgeEntries(
  all: KnowledgeEntry[],
  options?: { kind?: string; q?: string },
): KnowledgeEntry[] {
  const kind = options?.kind;
  const q = options?.q?.trim() ?? "";
  return all.filter(
    (entry) =>
      (!kind || kind === "all" || entry.kind === kind) && (q === "" || matches(entry, q)),
  );
}

export function listMockKnowledge(options?: { kind?: string; q?: string }): KnowledgeEntry[] {
  return filterKnowledgeEntries(entries, options);
}

// A deep copy of every entry: drafts start from the published list without
// touching it.
export function snapshotMockKnowledge(): KnowledgeEntry[] {
  return JSON.parse(JSON.stringify(entries)) as KnowledgeEntry[];
}

export function getMockKnowledge(key: string): KnowledgeEntry | undefined {
  return entries.find((entry) => entry.key === key);
}

export interface MockSuggestion {
  key: string;
  text: string;
  at: string;
}

const suggestions: MockSuggestion[] = [];

// Record a suggestion (mock only). The displayed published entry never
// changes; the learner picks suggestions up later (P12.2).
export function suggestMockChange(key: string, text: string): "ok" | "not_found" | "bad_text" {
  if (getMockKnowledge(key) === undefined) return "not_found";
  if (text.trim() === "") return "bad_text";
  suggestions.push({ key, text: text.trim(), at: new Date().toISOString() });
  return "ok";
}

export function mockSuggestions(): MockSuggestion[] {
  return [...suggestions];
}

// Fake "still learning" state for tests (mock only, like P03.12's warning and
// paused states). When set, /api/status reports no published knowledge and
// asking gets still_learning.
const STILL_LEARNING_KEY = "charie-mock-still-learning";

export function stillLearningOverride(): boolean {
  try {
    return localStorage.getItem(STILL_LEARNING_KEY) === "1";
  } catch {
    return false;
  }
}

export function resetMockKnowledge(): void {
  suggestions.length = 0;
  try {
    localStorage.removeItem(STILL_LEARNING_KEY);
  } catch {
    // Nothing to clear.
  }
}
