import type { OwnerQuestion } from "../questions/types";

// Sample owner questions (mock only). The three waiting questions match the
// Calm questions design; answered and skipped seeds fill the other tabs.
// Real processing is P09.5-P09.6. Sample data never enters the production bundle.
const waiting: OwnerQuestion[] = [
  {
    id: 1,
    status: "waiting",
    rank: 1,
    importance: "Affects about 40% of questions",
    topic: "Business word",
    title: 'What should "sales" mean by default?',
    evidence: {
      summary:
        "Two documents disagree. The **Finance wiki (2026)** includes delivery fees. The **Ops handbook (2024)** leaves them out.",
      docs: [
        { name: 'Finance wiki - "Net sales"', quote: "Net sales is the order value after discounts, before tax." },
        { name: "Ops handbook - page 12", quote: "Sales are reported without delivery fees." },
      ],
    },
    options: [
      {
        id: "with-fees",
        label: "Including delivery fees",
        number: "$1.42M",
        explanation: "Matches the Finance wiki",
      },
      {
        id: "without-fees",
        label: "Without delivery fees",
        number: "$1.31M",
        explanation: "Matches the Ops handbook",
      },
      {
        id: "ask-each-time",
        label: "Ask me each time",
        explanation: "Charie shows both numbers when it's unclear",
      },
    ],
    defaultOption: "with-fees",
    defaultReason: "Numbers are for 1-26 Oct. If you skip this, Charie uses “Including delivery fees”, because the Finance wiki is newer.",
    affects: ["metric.net_sales"],
    source: "learning",
  },
  {
    id: 2,
    status: "waiting",
    rank: 2,
    importance: "Affects every sales number",
    topic: "Data",
    title: "Are restaurants 9000-9099 test restaurants?",
    evidence: {
      summary: "They have orders but no address, no staff and no opening hours.",
      table: {
        columns: ["Restaurant", "Orders", "Address"],
        rows: [
          ["9001 - Test Kitchen A", 412, "empty"],
          ["9002 - Test Kitchen B", 389, "empty"],
          ["…and 4 more", 1207, "empty"],
        ],
      },
    },
    options: [
      {
        id: "leave-out",
        label: "Yes, leave them out of every number",
        number: "$1.42M",
        explanation: "Sales without them, 1-26 Oct",
      },
      {
        id: "count-them",
        label: "No, they're real. Count them.",
        number: "$1.47M",
        explanation: "Sales with them, 1-26 Oct",
      },
    ],
    defaultOption: "leave-out",
    defaultReason: "If you skip this, Charie leaves them out and adds a note to answers that touch them.",
    affects: ["metric.net_sales", "data_problem.late_orders"],
    source: "learning",
  },
  {
    id: 3,
    status: "waiting",
    rank: 3,
    importance: "Affects coupon questions",
    topic: "Codes",
    title: "Do the last 4 digits of a coupon code mean month and year?",
    evidence: {
      summary:
        'All 21 coupon codes end in 4 digits, like **MEGA0926** and **LUNCH1026**. The promotions calendar has a "MEGA deal" in September 2026.',
    },
    options: [
      { id: "yes-digits", label: "Yes: 0926 means September 2026" },
      { id: "no-digits", label: "No" },
      {
        id: "other",
        label: "Something else",
        explanation: "Tell Charie in your own words",
      },
    ],
    allowText: "other",
    defaultOption: "no-digits",
    affects: ["default.coupon_codes"],
    source: "refresh",
  },
];

const answered: OwnerQuestion[] = [
  {
    id: 11,
    status: "answered",
    rank: 4,
    importance: "Affects time questions",
    topic: "Business word",
    title: 'What does "last week" mean?',
    evidence: { summary: "Answers used both calendar weeks and rolling 7 days." },
    options: [
      { id: "mon-sun", label: "Last full week, Monday to Sunday" },
      { id: "rolling", label: "The last 7 days" },
    ],
    defaultOption: "mon-sun",
    answer: { optionId: "mon-sun" },
    answeredAt: "2025-10-24T09:12:00Z",
    source: "learning",
  },
  {
    id: 12,
    status: "answered",
    rank: 5,
    importance: "Affects table questions",
    topic: "Tables",
    title: "Is the orders_old table still used?",
    evidence: { summary: "Nothing has read it since March." },
    options: [
      { id: "unused", label: "No, it's out of date. Don't use it." },
      { id: "keep", label: "Yes, keep using it" },
    ],
    defaultOption: "unused",
    answer: { optionId: "unused" },
    answeredAt: "2025-10-23T15:40:00Z",
    source: "learning",
  },
  {
    id: 13,
    status: "answered",
    rank: 6,
    importance: "Affects change questions",
    topic: "Rules",
    title: "How big a change should Charie point out?",
    evidence: { summary: "Small wobbles are noise; owners care past a threshold." },
    options: [
      { id: "five", label: "More than 5%, or more than $5K" },
      { id: "ten", label: "More than 10%, or more than $10K" },
    ],
    defaultOption: "five",
    answer: { optionId: "five" },
    answeredAt: "2025-10-22T11:05:00Z",
    source: "nightly",
  },
];

const skipped: OwnerQuestion[] = [
  {
    id: 21,
    status: "skipped",
    rank: 7,
    importance: "Affects delivery questions",
    topic: "Events",
    title: "Was the Austin outage a one-off?",
    evidence: {
      summary: "The delivery app was down **14 Oct 6:20 pm to 16 Oct 9:05 pm**.",
      docs: [{ name: "Incident log.docx - page 2" }],
    },
    options: [
      { id: "one-off", label: "Yes, ignore it in trends" },
      { id: "pattern", label: "No, watch for repeats" },
    ],
    defaultOption: "one-off",
    defaultReason: "Skipped. Charie treats it as a one-off for now.",
    source: "refresh",
  },
];

export const seedQuestions: OwnerQuestion[] = [...waiting, ...answered, ...skipped];

interface QuestionPatch {
  status: "answered" | "skipped";
  answer?: { optionId?: string; text?: string };
  answeredAt?: string | null;
}

const QUESTIONS_KEY = "charie-mock-questions";

function questionStorage(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

function readPatches(): Map<number, QuestionPatch> {
  const out = new Map<number, QuestionPatch>();
  const store = questionStorage();
  if (store === null) return out;
  try {
    const raw = store.getItem(QUESTIONS_KEY);
    if (!raw) return out;
    const data = JSON.parse(raw) as Record<string, QuestionPatch>;
    for (const [key, patch] of Object.entries(data)) {
      const id = Number(key);
      if (!Number.isInteger(id)) continue;
      if (patch?.status === "answered" || patch?.status === "skipped") out.set(id, patch);
    }
  } catch {
    // A corrupt store starts fresh.
  }
  return out;
}

function writePatches(patches: Map<number, QuestionPatch>): void {
  const store = questionStorage();
  if (store === null) return;
  try {
    store.setItem(QUESTIONS_KEY, JSON.stringify(Object.fromEntries(patches)));
  } catch {
    // Test-only state; ignore.
  }
}

// Explicit badge override for tests (mock only). When unset, the badge
// follows the live waiting-question count.
const WAITING_OVERRIDE_KEY = "charie-mock-waiting-override";
export function waitingOverride(): number | null {
  const store = questionStorage();
  if (store === null) return null;
  try {
    const raw = store.getItem(WAITING_OVERRIDE_KEY);
    if (raw === null) return null;
    const n = Number(raw);
    return Number.isInteger(n) && n >= 0 ? n : null;
  } catch {
    return null;
  }
}

// Test-only reset for the questions store.
export function resetMockQuestions(): void {
  const store = questionStorage();
  if (store === null) return;
  try {
    store.removeItem(QUESTIONS_KEY);
    store.removeItem(WAITING_OVERRIDE_KEY);
  } catch {
    // Nothing to clear.
  }
}

function currentQuestions(): OwnerQuestion[] {
  const patches = readPatches();
  return seedQuestions.map((seed) => {
    const patch = patches.get(seed.id);
    if (!patch) return seed;
    return { ...seed, status: patch.status, answer: patch.answer, answeredAt: patch.answeredAt };
  });
}

export function listMockQuestions(status?: "waiting" | "answered" | "skipped"): OwnerQuestion[] {
  const all = currentQuestions().sort((a, b) => a.rank - b.rank);
  return status ? all.filter((q) => q.status === status) : all;
}

export function waitingMockCount(): number {
  return currentQuestions().filter((q) => q.status === "waiting").length;
}

// Answer a waiting question (mock only). Exactly one of optionId/text;
// unknown options and empty text are refused like the real API.
export function answerMockQuestion(
  id: number,
  answer: { optionId: string } | { text: string },
): "ok" | "not_found" | "bad_answer" {
  const patches = readPatches();
  const base = seedQuestions.find((q) => q.id === id);
  if (!base && !patches.has(id)) return "not_found";
  if ("optionId" in answer) {
    if (!base || !base.options.some((o) => o.id === answer.optionId)) return "bad_answer";
    patches.set(id, {
      status: "answered",
      answer: { optionId: answer.optionId },
      answeredAt: new Date().toISOString(),
    });
  } else {
    if (answer.text.trim() === "") return "bad_answer";
    patches.set(id, {
      status: "answered",
      answer: { text: answer.text.trim() },
      answeredAt: new Date().toISOString(),
    });
  }
  writePatches(patches);
  return "ok";
}

// Skip a waiting question (mock only). The documented default stays in force.
export function skipMockQuestion(id: number): "ok" | "not_found" {
  const patches = readPatches();
  const known = seedQuestions.some((q) => q.id === id) || patches.has(id);
  if (!known) return "not_found";
  patches.set(id, { status: "skipped" });
  writePatches(patches);
  return "ok";
}
