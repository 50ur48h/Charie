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
  pages: number;
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
