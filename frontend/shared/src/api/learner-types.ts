import type { KnowledgeEntry } from "../knowledge/types";

// Learner API bodies (architecture 09, learner addresses). P04.1 writes them;
// Phases 5, 7, 8 and 9 build the back end to match (C005: this file wins).

// One row of the documents table (05 section 2), plus id. progress is 0–100
// while reading and null otherwise — there is no progress column, so the
// API works it out. unreadable_pages counts pages the reader gave up on.
export type LearnerDocumentStatus = "new" | "reading" | "learned" | "failed" | "removed";

export interface LearnerDocument {
  id: number;
  file_name: string;
  file_type: string;
  size_bytes: number;
  pages: number | null; // null while the reader hasn't counted them yet.
  unreadable_pages: number;
  fact_count: number;
  status: LearnerDocumentStatus;
  progress: number | null;
  error: string | null;
  uploaded_at: string;
  learned_at: string | null;
}

// One learning run (05 section 5). step is 1–12 (the steps in 02);
// minutes_left and finished_at are null while running.
export type LearningRunKind = "first" | "refresh" | "nightly";
export type LearningRunStatus = "running" | "paused" | "done" | "failed";

export interface StepProgress {
  step: number;
  done: number;
  total: number | null;
  note: string;
}

export interface LearningRun {
  id: number;
  kind: LearningRunKind;
  status: LearningRunStatus;
  reason: string | null;
  step: number;
  percent: number;
  minutes_left: number | null;
  progress: StepProgress[];
  cost_usd: number;
  summary: string | null;
  version_number: number;
  new_version: boolean;
  started_at: string;
  finished_at: string | null;
}

// GET /api/learning: the runs, newest first.
export interface LearningOverview {
  runs: LearningRun[];
}

// GET /api/setup (setup guide state). step is 1-5, the first step that is not
// complete; readiness is the step-5 report, null until learning finishes it.
export interface Readiness {
  numbers_checked: number;
  numbers_total: number;
  numbers_waiting: number;
  practice_right: number;
  practice_total: number;
  weak_area: string | null;
  weak_area_why: string | null;
}

export interface SetupState {
  setup_done: boolean;
  step: number;
  readiness: Readiness | null;
}

// GET /api/sources/database: the saved connection. The API never sends the
// password back; details holds the table and row counts from the last check.
export type DatabaseKind = "postgres";
export type DatabaseStatus = "connected" | "failed";

export interface DatabaseSource {
  kind: DatabaseKind;
  name: string;
  host: string;
  port: number;
  database: string;
  username: string;
  status: DatabaseStatus;
  read_only_ok: boolean;
  data_through: string | null;
  checked_at: string | null;
  details: { tables: number; rows: number };
}

// PUT /api/sources/database. An empty password keeps the saved one.
export interface DatabaseInput {
  kind: DatabaseKind;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
}

// POST /api/sources/database/test: the connection check result.
export interface ConnectionTest {
  read_only_ok: boolean;
  data_through: string;
  details: { tables: number; rows: number };
}

// GET /api/owner-notes and PUT /api/owner-notes { text }. The server keeps
// the last sorted columns until learning sorts the new text.
export interface SortedNotes {
  hard_rules: string[];
  style_rules: string[];
  data_hints: string[];
}

export interface OwnerNotes {
  text: string;
  saved_at: string | null;
  sorted: SortedNotes | null;
  sorted_at: string | null;
}

// GET /api/learning/stream (architecture 09): the live feed. `at` is when
// Charie found it; `step` is the 1-12 learning step; `seq` numbers the
// lines so the client skips ones it already saw (Last-Event-ID).
export type LearningEventKind = "info" | "found" | "question" | "warning" | "done";

export interface LearningEvent {
  seq: number;
  at: string;
  step: number;
  kind: LearningEventKind;
  message: string;
}
// A knowledge version (architecture 02, "Versions"): a full copy of the
// entries. Only one version is published at a time; the draft waits for
// the owner unless every change is small (P04.9 auto-publishes; the mock
// always waits).
export interface KbVersion {
  id: number;
  number: number;
  status: "draft" | "published" | "archived";
  made_by: "first_learning" | "refresh" | "nightly" | "owner_edit";
  created_at: string;
  published_at: string | null;
  summary: { added: number; changed: number; removed: number; note: string };
}

// What changed in one version, for Review changes. `before` and `after`
// are entries, or null when the entry is new or gone.
export interface KbChange {
  key: string;
  title: string;
  change: "added" | "changed" | "removed";
  before: KnowledgeEntry | null;
  after: KnowledgeEntry | null;
  reason: string;
  is_big: boolean;
}

// One item on the learner's to-do list (Mark as wrong, or a correction
// from a chat). Open items show on the Knowledge page.
export interface LearnerTodo {
  id: number;
  kind: "correction" | "unknown_word" | "new_metric" | "meaning_change";
  text: string;
  details: { chat_title: string | null; words: string | null };
  status: "open" | "done" | "dismissed";
  result: string | null;
  created_at: string;
  done_at: string | null;
}