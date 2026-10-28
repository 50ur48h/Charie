import type { KnowledgeEntry } from "../knowledge/types";

// Sample knowledge entries (mock only), matching the Calm knowledge design.
// The design's ids differ from the stable fixture keys the plans require, so
// KEY_MAP translates them: metric.net_sales, metric.food_cost_percent,
// default.lunch and data_problem.late_orders keep their keys everywhere.
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
    kind: "number",
    name: "Net sales",
    confidence: "owner",
    used: 32,
    short: "Order total minus tax, delivery fee and discounts. Completed orders only.",
    meaning:
      'What the restaurants actually earned from food and drink. When someone just says "sales", this is what Charie uses.',
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
    kind: "number",
    name: "Average order",
    confidence: "data",
    used: 18,
    short: "Net sales divided by the number of completed orders. Never an average of averages.",
  },
  {
    key: "metric.food_cost_percent",
    kind: "number",
    name: "Food cost %",
    confidence: "doc",
    used: 6,
    short: "Ingredient cost as a share of net sales. Target is 28-31%.",
  },
  {
    key: "metric.labor_cost_percent",
    kind: "number",
    name: "Labor cost %",
    confidence: "guess",
    used: 2,
    short: "Staff cost as a share of net sales. The formula isn't confirmed yet.",
  },
  {
    key: "default.sales_word",
    kind: "word",
    name: '"Sales"',
    confidence: "conflict",
    used: 41,
    short: "Two documents disagree about delivery fees. There's a question waiting for you.",
  },
  {
    key: "default.last_week",
    kind: "word",
    name: '"Last week"',
    confidence: "owner",
    used: 14,
    short: "The last full week, Monday to Sunday.",
  },
  {
    key: "default.lunch",
    kind: "word",
    name: '"Lunch"',
    confidence: "doc",
    used: 5,
    short: "Orders placed between 11 am and 3 pm.",
  },
  {
    key: "data.orders_total",
    kind: "table",
    name: "orders.total",
    confidence: "data",
    used: 29,
    short: "The full order amount in US dollars, including tax and the delivery fee.",
  },
  {
    key: "data.order_items",
    kind: "table",
    name: "order_items",
    confidence: "data",
    used: 11,
    short: "One row per dish in an order. Never add up order totals after joining this table.",
  },
  {
    key: "rule.test_stores",
    kind: "rule",
    name: "Leave out test restaurants",
    confidence: "guess",
    used: 41,
    short: "Restaurants 9000-9099 look like tests. There's a question waiting for you.",
  },
  {
    key: "rule.usd_only",
    kind: "rule",
    name: "Money is always in US dollars",
    confidence: "owner",
    used: 41,
    short: "From your notes: never convert currencies.",
  },
  {
    key: "default.coupon_codes",
    kind: "code",
    name: "Coupon codes like MEGA0926",
    confidence: "guess",
    used: 3,
    short: "The last 4 digits look like month and year. There's a question waiting for you.",
  },
  {
    key: "event.austin_outage",
    kind: "event",
    name: "Delivery app outage, Austin",
    confidence: "doc",
    used: 2,
    short: "14 Oct 6:20 pm to 16 Oct 9:05 pm. From the incident log.",
  },
  {
    key: "data_problem.late_orders",
    kind: "problem",
    name: "Late orders from 3 restaurants",
    confidence: "data",
    used: 1,
    short: "On 20 Oct, orders from 3 restaurants arrived a day late.",
  },
];

export function keyToEntryKey(key: string): string {
  return KEY_MAP[key] ?? key;
}

function matches(entry: KnowledgeEntry, query: string): boolean {
  const hay = `${entry.name} ${entry.short} ${entry.meaning ?? ""}`.toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter((word) => word.length > 0)
    .every((word) => hay.includes(word));
}

export function listMockKnowledge(options?: { kind?: string; q?: string }): KnowledgeEntry[] {
  const kind = options?.kind;
  const q = options?.q?.trim() ?? "";
  return entries.filter(
    (entry) =>
      (!kind || kind === "all" || entry.kind === kind) && (q === "" || matches(entry, q)),
  );
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

export function resetMockKnowledge(): void {
  suggestions.length = 0;
}
