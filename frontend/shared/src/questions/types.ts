// Owner questions (architecture 05 `owner_questions`, 09 addresses).
// Shared by the chat Questions page and the learner setup step.
export type QuestionStatus = "waiting" | "answered" | "skipped";

export interface QuestionOption {
  id: string;
  label: string;
  /** The number this option gives, filled in by code (for example "$1.42M"). */
  number?: string;
  explanation?: string;
}

export interface QuestionDoc {
  name: string;
  quote?: string;
}

export interface QuestionTable {
  columns: string[];
  rows: (string | number)[][];
}

export interface Evidence {
  /** Plain text; **bold** spans render emphasized. */
  summary: string;
  docs?: QuestionDoc[];
  table?: QuestionTable;
}

export interface OwnerQuestion {
  id: number;
  status: QuestionStatus;
  rank: number;
  importance: string;
  topic: string;
  title: string;
  body?: string;
  evidence: Evidence;
  options: QuestionOption[];
  /** True when one option collects free text ("Something else"). */
  allowText?: string;
  defaultOption: string;
  defaultReason?: string;
  answer?: { optionId?: string; text?: string };
  answeredAt?: string | null;
  affects?: string[];
  source?: string;
}

export interface QuestionListResponse {
  questions: OwnerQuestion[];
}
