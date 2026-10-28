// Thinking fixtures for the fake API: running, finished, failed and empty
// timelines with the evidence the panel shows. Sample data lives only here,
// never in the production bundle.
import type { ThinkingLine, ThinkingSummary } from "../answer/thinking";

export const runningThinking: ThinkingLine[] = [
  {
    seq: 1,
    kind: "decision",
    status: "done",
    title: "Understood the question",
    body: "Comparing October with September, profit by dish.",
  },
  {
    seq: 2,
    kind: "query",
    status: "running",
    title: "Adding up profit by dish",
    details: { sql: "SELECT dish, SUM(profit) FROM sales GROUP BY dish" },
  },
];

export const finishedThinking: ThinkingLine[] = [
  {
    seq: 1,
    kind: "decision",
    status: "done",
    title: "Understood the question",
    body: "Net sales, orders and average order for October vs September.",
  },
  {
    seq: 2,
    kind: "query",
    status: "done",
    title: "Added up sales by restaurant",
    details: { sql: "SELECT restaurant, SUM(net) FROM sales GROUP BY restaurant" },
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
  },
  {
    seq: 4,
    kind: "check",
    status: "done",
    title: "Checked every number",
    details: { note: "Each figure matches the database extract." },
  },
];

export const finishedSummary: ThinkingSummary = {
  seconds: 38,
  steps: 8,
  queries: 4,
  documents: 1,
};

export const failedThinking: ThinkingLine[] = [
  {
    seq: 1,
    kind: "query",
    status: "done",
    title: "Added up sales by day",
    details: { sql: "SELECT day, SUM(net) FROM sales GROUP BY day" },
  },
  {
    seq: 2,
    kind: "check",
    status: "failed",
    title: "Checking the weekend split",
    body: "The sales extract stopped updating on 24 Oct, so these numbers leave out the last two days.",
  },
];

export const emptyThinking: ThinkingLine[] = [];
