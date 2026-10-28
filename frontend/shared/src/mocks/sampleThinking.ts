// Thinking fixtures for the fake API: running, finished, failed and empty
// timelines with the evidence the panel shows. `at` marks when each line was
// saved, oldest first. Sample data lives only here, never in the production
// bundle.
import type { ThinkingLine, ThinkingSummary } from "../answer/thinking";

export const runningThinking: ThinkingLine[] = [
  {
    seq: 1,
    kind: "decision",
    status: "done",
    title: "Understood the question",
    body: "Comparing October with September, profit by dish.",
    at: "2025-10-26T12:00:00Z",
  },
  {
    seq: 2,
    kind: "query",
    status: "running",
    title: "Adding up profit by dish",
    details: { sql: "SELECT dish, SUM(profit) FROM sales GROUP BY dish" },
    at: "2025-10-26T12:00:04Z",
  },
];

export const finishedThinking: ThinkingLine[] = [
  {
    seq: 1,
    kind: "step",
    status: "done",
    title: "Understood the question",
    body: "Net sales, orders and average order for October vs September.",
    at: "2025-10-26T12:00:00Z",
  },
  {
    seq: 2,
    kind: "query",
    status: "done",
    title: "Added up sales by restaurant",
    details: { sql: "SELECT restaurant, SUM(net) FROM sales GROUP BY restaurant" },
    at: "2025-10-26T12:00:09Z",
  },
  {
    seq: 3,
    kind: "document",
    status: "done",
    title: "Read the incident log",
    details: {
      document: "Incident log.docx",
      quote: "Downtown delivery was down between 6 and 9 pm.",
      location: "page 2",
    },
    at: "2025-10-26T12:00:15Z",
  },
  {
    seq: 4,
    kind: "found",
    status: "done",
    title: "Found the Downtown outage",
    body: "Delivery orders fell $17.2K during the outage hours.",
    at: "2025-10-26T12:00:21Z",
  },
  {
    seq: 5,
    kind: "check",
    status: "done",
    title: "Checked every number",
    details: { note: "Each figure matches the database extract." },
    at: "2025-10-26T12:00:30Z",
  },
];

export const finishedSummary: ThinkingSummary = {
  seconds: 38,
  steps: 8,
  queries: 4,
  documents: 1,
};

// The follow-up in seed chat 1 keeps its own evidence, separate from the
// first answer's panel above it.
export const secondThinking: ThinkingLine[] = [
  {
    seq: 1,
    kind: "decision",
    status: "done",
    title: "Understood the follow-up",
    body: "Same figures for last year.",
    at: "2025-10-26T12:05:00Z",
  },
  {
    seq: 2,
    kind: "query",
    status: "done",
    title: "Adding up last year's sales",
    details: { sql: "SELECT restaurant, SUM(net) FROM sales_2024 GROUP BY restaurant" },
    at: "2025-10-26T12:05:07Z",
  },
];

export const secondSummary: ThinkingSummary = {
  seconds: 21,
  steps: 5,
  queries: 2,
  documents: 0,
};

export const failedThinking: ThinkingLine[] = [
  {
    seq: 1,
    kind: "query",
    status: "done",
    title: "Added up sales by day",
    details: { sql: "SELECT day, SUM(net) FROM sales GROUP BY day" },
    at: "2025-10-26T12:00:00Z",
  },
  {
    seq: 2,
    kind: "check",
    status: "failed",
    title: "Checking the weekend split",
    body: "The sales extract stopped updating on 24 Oct, so these numbers leave out the last two days.",
    at: "2025-10-26T12:00:06Z",
  },
];

export const emptyThinking: ThinkingLine[] = [];
