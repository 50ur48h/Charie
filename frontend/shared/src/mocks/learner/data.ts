import type { LearnerDocument, LearningRun, StepProgress } from "../../api/learner-types";

// Learner sample worlds (mock only). The design world mirrors the Calm
// learner-sources design: 14 documents (286 pages) and 4 past learning runs.
// The new world is empty. Times carry +05:30; specs run in Asia/Kolkata.
const PLUS = "+05:30";

export interface LearnerWorld {
  documents: LearnerDocument[];
  runs: LearningRun[];
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

export function designWorld(): LearnerWorld {
  const seeds = [...DESIGN_ROWS, ...MORE_ROWS];
  return { documents: seeds.map((seed, i) => toDocument(seed, i + 1)), runs: designRuns() };
}

export function newWorld(): LearnerWorld {
  return { documents: [], runs: [] };
}
