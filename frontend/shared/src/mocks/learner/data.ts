import type {
  KbChange,
  KbVersion,
  LearnerDocument,
  LearnerTodo,
  LearningRun,
  StepProgress,
} from "../../api/learner-types";
import type { KnowledgeEntry } from "../../knowledge/types";
import { snapshotMockKnowledge } from "../sampleKnowledge";

// Learner sample worlds (mock only). The design world mirrors the Calm
// learner-sources design: 14 documents (286 pages) and 4 past learning runs.
// The new world is empty. Times carry +05:30; specs run in Asia/Kolkata.
const PLUS = "+05:30";

export interface LearnerWorld {
  documents: LearnerDocument[];
  runs: LearningRun[];
  versions: KbVersion[];
  draftEntries: KnowledgeEntry[] | null;
  publishedEntries: KnowledgeEntry[] | null;
  changesByVersion: Record<number, KbChange[]>;
  todos: LearnerTodo[];
  // What the last successful refresh consumed (mock only): removed document
  // ids already handled, and the notes save they included.
  refresh_consumed?: { removed: number[]; notes_at: string | null };
}

interface DocSeed {
  file_name: string;
  pages: number;
  uploaded_at: string;
  status: LearnerDocument["status"];
  fact_count?: number;
  unreadable_pages?: number;
  progress?: number;
  learned_at?: string;
  size_bytes: number;
}

function ext(name: string): string {
  return name.slice(name.lastIndexOf(".") + 1).toLowerCase();
}

// The 7 design table rows, newest first.
const DESIGN_ROWS: DocSeed[] = [
  { file_name: "Promotions calendar 2026.xlsx", pages: 3, uploaded_at: `2026-10-27T21:05:00${PLUS}`, status: "new", size_bytes: 18432 },
  { file_name: "Refund policy.docx", pages: 4, uploaded_at: `2026-10-27T21:04:00${PLUS}`, status: "new", size_bytes: 24576 },
  { file_name: "Menu guide, autumn.pdf", pages: 12, uploaded_at: `2026-10-27T21:02:00${PLUS}`, status: "reading", progress: 64, size_bytes: 1048576 },
  { file_name: "Incident log, Oct 2026.docx", pages: 6, uploaded_at: `2026-10-20T14:30:00${PLUS}`, status: "learned", fact_count: 9, learned_at: `2026-10-20T14:41:00${PLUS}`, size_bytes: 38912 },
  { file_name: "Finance wiki.pdf", pages: 24, uploaded_at: `2026-10-03T10:02:00${PLUS}`, status: "learned", fact_count: 41, learned_at: `2026-10-03T10:20:00${PLUS}`, size_bytes: 2097152 },
  { file_name: "Ops handbook 2024.docx", pages: 61, uploaded_at: `2026-10-03T10:01:00${PLUS}`, status: "learned", fact_count: 88, learned_at: `2026-10-03T10:35:00${PLUS}`, size_bytes: 3145728 },
  { file_name: "Supplier contract scan.pdf", pages: 9, uploaded_at: `2026-10-03T10:00:00${PLUS}`, status: "learned", fact_count: 5, unreadable_pages: 2, learned_at: `2026-10-03T10:12:00${PLUS}`, size_bytes: 1572864 },
];

// 7 more learned documents from 3 Oct (pages · facts as in the plan).
const MORE_ROWS: DocSeed[] = [
  { file_name: "Board report Q3 2026.pptx", pages: 64, uploaded_at: `2026-10-03T09:58:00${PLUS}`, status: "learned", fact_count: 31, learned_at: `2026-10-03T11:02:00${PLUS}`, size_bytes: 4194304 },
  { file_name: "Staff handbook.docx", pages: 44, uploaded_at: `2026-10-03T09:56:00${PLUS}`, status: "learned", fact_count: 51, learned_at: `2026-10-03T11:20:00${PLUS}`, size_bytes: 2621440 },
  { file_name: "Delivery partner agreement.pdf", pages: 18, uploaded_at: `2026-10-03T09:54:00${PLUS}`, status: "learned", fact_count: 22, learned_at: `2026-10-03T10:48:00${PLUS}`, size_bytes: 1310720 },
  { file_name: "Kitchen waste guide.pdf", pages: 16, uploaded_at: `2026-10-03T09:52:00${PLUS}`, status: "learned", fact_count: 19, learned_at: `2026-10-03T10:44:00${PLUS}`, size_bytes: 1048576 },
  { file_name: "Loyalty programme.pdf", pages: 12, uploaded_at: `2026-10-03T09:50:00${PLUS}`, status: "learned", fact_count: 14, learned_at: `2026-10-03T10:40:00${PLUS}`, size_bytes: 786432 },
  { file_name: "Pricing policy.docx", pages: 8, uploaded_at: `2026-10-03T09:48:00${PLUS}`, status: "learned", fact_count: 11, learned_at: `2026-10-03T10:36:00${PLUS}`, size_bytes: 196608 },
  { file_name: "Supplier list 2026.xlsx", pages: 5, uploaded_at: `2026-10-03T09:46:00${PLUS}`, status: "learned", fact_count: 6, learned_at: `2026-10-03T10:32:00${PLUS}`, size_bytes: 98304 },
];

function toDocument(seed: DocSeed, id: number): LearnerDocument {
  return {
    id,
    file_name: seed.file_name,
    file_type: ext(seed.file_name),
    size_bytes: seed.size_bytes,
    pages: seed.pages,
    unreadable_pages: seed.unreadable_pages ?? 0,
    fact_count: seed.fact_count ?? 0,
    status: seed.status,
    progress: seed.status === "reading" ? (seed.progress ?? 0) : null,
    error: null,
    uploaded_at: seed.uploaded_at,
    learned_at: seed.learned_at ?? null,
  };
}

// Every step of a done run is 1 of 1 with an empty note; run 4's progress
// starts empty and P04.7 fills it.
// Run 4's design progress (P04.7 table): label, done and total per step.
export function designRunProgress(): StepProgress[] {
  return [
    { step: 1, done: 18, total: 18, note: "18 rules and hints" },
    { step: 2, done: 57, total: 57, note: "57 tables, 412 columns" },
    { step: 3, done: 57, total: 57, note: "Empty values, common values, date ranges" },
    { step: 4, done: 61, total: 61, note: "61 links between tables" },
    { step: 5, done: 14, total: 14, note: "14 documents, 612 sections" },
    { step: 6, done: 312, total: null, note: "312 facts, 4 disagreements" },
    { step: 7, done: 57, total: 57, note: "57 tables explained in plain words" },
    { step: 8, done: 31, total: 45, note: 'Testing "average order" · 31 of 45' },
    { step: 9, done: 0, total: null, note: "Waiting" },
    { step: 10, done: 2, total: null, note: "Waiting" },
    { step: 11, done: 0, total: 200, note: "200 practice questions" },
    { step: 12, done: 0, total: 1, note: "Publish version 15" },
  ];
}
function fullSteps(): StepProgress[] {
  return Array.from({ length: 12 }, (_, i) => ({ step: i + 1, done: 1, total: 1, note: "" }));
}

function designRuns(): LearningRun[] {
  return [
    {
      id: 4,
      kind: "refresh",
      status: "running",
      paused_by: null,
      reason: "3 new documents",
      step: 8,
      percent: 62,
      minutes_left: 25,
      progress: designRunProgress(),
      cost_usd: 3.8,
      summary: "6 changes",
      version_number: 15,
      new_version: true,
      started_at: `2026-10-27T21:12:00${PLUS}`,
      finished_at: null,
    },
    {
      id: 3,
      kind: "nightly",
      status: "done",
      paused_by: null,
      reason: null,
      step: 12,
      percent: 100,
      minutes_left: null,
      progress: fullSteps(),
      cost_usd: 1.2,
      summary: "No changes",
      version_number: 14,
      new_version: false,
      started_at: `2026-10-26T02:00:00${PLUS}`,
      finished_at: `2026-10-26T02:04:00${PLUS}`,
    },
    {
      id: 2,
      kind: "nightly",
      status: "done",
      paused_by: null,
      reason: null,
      step: 12,
      percent: 100,
      minutes_left: null,
      progress: fullSteps(),
      cost_usd: 2.1,
      summary: "2 new coupon codes, 1 new restaurant",
      version_number: 14,
      new_version: true,
      started_at: `2026-10-20T02:00:00${PLUS}`,
      finished_at: `2026-10-20T02:06:00${PLUS}`,
    },
    {
      id: 1,
      kind: "first",
      status: "done",
      paused_by: null,
      reason: null,
      step: 12,
      percent: 100,
      minutes_left: null,
      progress: fullSteps(),
      cost_usd: 18.4,
      summary: "236 entries, 12 questions for you",
      version_number: 1,
      new_version: true,
      started_at: `2026-10-03T10:05:00${PLUS}`,
      finished_at: `2026-10-03T11:53:00${PLUS}`,
    },
  ];
}

// The 15 design versions, newest first (P04.8 table).
function designVersions(): KbVersion[] {
  const versions: KbVersion[] = [
    {
      id: 15,
      number: 15,
      status: "draft",
      made_by: "refresh",
      created_at: `2026-10-27T21:12:00${PLUS}`,
      published_at: null,
      summary: {
        added: 3,
        changed: 2,
        removed: 1,
        note: "3 new facts from new documents · 2 updated meanings · 1 removed",
      },
    },
    {
      id: 14,
      number: 14,
      status: "published",
      made_by: "nightly",
      created_at: `2026-10-20T02:00:00${PLUS}`,
      published_at: `2026-10-20T02:06:00${PLUS}`,
      summary: { added: 2, changed: 0, removed: 0, note: "2 new coupon codes, 1 new restaurant" },
    },
    {
      id: 13,
      number: 13,
      status: "archived",
      made_by: "owner_edit",
      created_at: `2026-10-16T10:00:00${PLUS}`,
      published_at: `2026-10-16T10:00:00${PLUS}`,
      summary: { added: 0, changed: 0, removed: 0, note: "Your answers to 12 questions" },
    },
  ];
  for (let number = 12; number >= 2; number -= 1) {
    const day = String(number + 2).padStart(2, "0");
    versions.push({
      id: number,
      number,
      status: "archived",
      made_by: "nightly",
      created_at: `2026-10-${day}T02:05:00${PLUS}`,
      published_at: `2026-10-${day}T02:05:00${PLUS}`,
      summary: { added: 0, changed: 0, removed: 0, note: "Small updates from the nightly check" },
    });
  }
  versions.push({
    id: 1,
    number: 1,
    status: "archived",
    made_by: "first_learning",
    created_at: `2026-10-03T10:05:00${PLUS}`,
    published_at: `2026-10-03T11:53:00${PLUS}`,
    summary: { added: 236, changed: 0, removed: 0, note: "236 entries, 12 questions for you" },
  });
  return versions;
}

// Draft 15's 6 changes (P04.8 table), on top of P03.11's published entries.
function designDraftChanges(published: KnowledgeEntry[]): KbChange[] {
  const byKey = new Map(published.map((entry) => [entry.key, entry]));
  const lunch = byKey.get("default.lunch");
  const foodCost = byKey.get("metric.food_cost_percent");
  const lateOrders = byKey.get("data_problem.late_orders");
  if (!lunch || !foodCost || !lateOrders) throw new Error("design entries are missing");
  const refunds: KnowledgeEntry = {
    key: "rule.refunds_out_of_sales",
    kind: "rule",
    title: "Refunds come out of sales",
    confidence: "from_document",
    used: 0,
    updated_at: null,
    meaning: "Refunds come out of sales; they are not separate income.",
    sources: [{ doc: "Refund policy.docx" }],
  };
  const dishes: KnowledgeEntry = {
    key: "name.autumn_menu_dishes",
    kind: "name",
    title: "Autumn menu dishes",
    confidence: "from_document",
    used: 0,
    updated_at: null,
    meaning: "6 new dishes from the autumn menu guide.",
    sources: [{ doc: "Menu guide, autumn.pdf" }],
  };
  const megaDeal: KnowledgeEntry = {
    key: "event.mega_deal_sep_2026",
    kind: "event",
    title: "MEGA deal, September 2026",
    confidence: "from_document",
    used: 0,
    updated_at: null,
    meaning: "A September 2026 promotion with coupon codes.",
    sources: [{ doc: "Promotions calendar 2026.xlsx" }],
  };
  return [
    {
      key: refunds.key,
      title: refunds.title,
      change: "added",
      before: null,
      after: refunds,
      reason: "Found in Refund policy.docx.",
      is_big: false,
    },
    {
      key: dishes.key,
      title: dishes.title,
      change: "added",
      before: null,
      after: dishes,
      reason: "Found in the autumn menu guide.",
      is_big: false,
    },
    {
      key: megaDeal.key,
      title: megaDeal.title,
      change: "added",
      before: null,
      after: megaDeal,
      reason: "Found in the promotions calendar.",
      is_big: false,
    },
    {
      key: lunch.key,
      title: lunch.title,
      change: "changed",
      before: lunch,
      after: {
        ...lunch,
        meaning: "Orders placed between 11 am and 2:30 pm.",
        confidence: "confirmed",
      },
      reason: "The autumn menu guide says lunch ends at 2:30 pm.",
      is_big: true,
    },
    {
      key: foodCost.key,
      title: foodCost.title,
      change: "changed",
      before: foodCost,
      after: {
        ...foodCost,
        meaning: "Ingredient cost as a share of net sales. Target is 28–30%.",
        confidence: "confirmed",
      },
      reason: "The autumn menu guide sets a new target.",
      is_big: false,
    },
    {
      key: lateOrders.key,
      title: lateOrders.title,
      change: "removed",
      before: lateOrders,
      after: null,
      reason: "The late orders arrived. The data is complete now.",
      is_big: false,
    },
  ];
}

// Version 14's 3 checked additions (P04.9 Review changes for old versions).
function version14Changes(): KbChange[] {
  const added = (
    key: string,
    name: string,
    meaning: string,
  ): { entry: KnowledgeEntry; title: string } => ({
    entry: {
      key,
      kind: "name",
      title: name,
      confidence: "confirmed",
      used: 0,
      updated_at: null,
      meaning,
      sources: [],
    },
    title: name,
  });
  const lunch = added("name.coupon_lunch1026", "Coupon code LUNCH1026", "The October lunch coupon code.");
  const fall = added("name.coupon_fall1026", "Coupon code FALL1026", "The October fall coupon code.");
  const roundRock = added(
    "name.round_rock_restaurant",
    "Restaurant: Round Rock",
    "A restaurant in Round Rock.",
  );
  return [lunch, fall, roundRock].map(({ entry, title }) => ({
    key: entry.key,
    title,
    change: "added",
    before: null,
    after: entry,
    reason: "Found by the nightly check.",
    is_big: false,
  }));
}

// The design world's 2 open to-do items (P04.9 table).
function designTodos(): LearnerTodo[] {
  return [
    {
      id: 1,
      kind: "correction",
      text: "Net sales should leave out refunds.",
      details: {
        chat_title: "How are we doing this month?",
        words: "Net sales should leave out refunds.",
      },
      status: "open",
      result: null,
      created_at: `2026-10-26T18:40:00${PLUS}`,
      done_at: null,
    },
    {
      id: 2,
      kind: "unknown_word",
      text: 'What is a "MEGA deal"?',
      details: { chat_title: "Top dishes by profit", words: 'What is a "MEGA deal"?' },
      status: "open",
      result: null,
      created_at: `2026-10-25T12:15:00${PLUS}`,
      done_at: null,
    },
  ];
}

// Draft 15's working copy: the published entries with its 6 changes applied.
function designDraftEntries(): KnowledgeEntry[] {
  const published = snapshotMockKnowledge();
  const changes = designDraftChanges(published);
  const draft = published.filter(
    (entry) => !changes.some((change) => change.change === "removed" && change.key === entry.key),
  );
  for (const entry of draft) {
    const change = changes.find((c) => c.change === "changed" && c.key === entry.key);
    if (change?.after) {
      entry.meaning = change.after.meaning;
      entry.confidence = change.after.confidence;
    }
  }
  for (const change of changes) {
    if (change.change === "added" && change.after) draft.push(change.after);
  }
  return draft;
}
export function designWorld(): LearnerWorld {
  const seeds = [...DESIGN_ROWS, ...MORE_ROWS];
  return {
    documents: seeds.map((seed, i) => toDocument(seed, i + 1)),
    runs: designRuns(),
    versions: designVersions(),
    draftEntries: designDraftEntries(),
    publishedEntries: null,
    changesByVersion: { 15: designDraftChanges(snapshotMockKnowledge()), 14: version14Changes() },
    todos: designTodos(),
  };
}

export function newWorld(): LearnerWorld {
  return { documents: [], runs: [], versions: [], draftEntries: null, publishedEntries: null, changesByVersion: {}, todos: [] };
}
