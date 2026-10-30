// Knowledge entries (architecture 09 addresses, design knowledge.js).
// Shared by the chat read-only page and the learner editor (P04.8).
// The list carries one short row per entry; the detail carries the full
// entry plus its version and history. Fields the API never sends
// (`used`, `how`, `sql`, `checks`, string `history`) only exist in the
// design mocks, where the existing evidence sections still render them.
export type KnowledgeKind =
  | "table"
  | "column"
  | "link"
  | "metric"
  | "dimension"
  | "rule"
  | "style"
  | "code"
  | "event"
  | "data_problem"
  | "default"
  | "calendar"
  | "how_to"
  | "example"
  | "name"
  | "data_range";

export type KnowledgeConfidence =
  | "confirmed"
  | "checked"
  | "from_document"
  | "guessed"
  | "conflicting";

export interface KnowledgeSource {
  /** Typed sources from the API (`structure`, `profile`, `query`, ...). */
  type?: string;
  /** The design mock's document name. */
  doc?: string;
  text?: string;
  quote?: string;
  sql?: string;
  at?: string;
}

export interface KnowledgeHistoryItem {
  version: number | null;
  change: string;
  reason: string;
}

export interface KnowledgeEntry {
  /** Stable key (for example "metric.net_sales"). Never a list index. */
  key: string;
  kind: KnowledgeKind;
  title: string;
  /** The list cuts this to 200 characters; the detail shows it whole. */
  meaning: string;
  confidence: KnowledgeConfidence;
  /** Kind-specific facts from the API (P07.3 details models). */
  details?: unknown;
  sources?: KnowledgeSource[];
  updated_at: string | null;
  /** Design-mock only: how many answers used this entry. */
  used?: number;
  /** Design-mock only: how the number is worked out. */
  how?: string[];
  /** Design-mock only: the recipe query behind `how`. */
  sql?: string;
  /** Design-mock only: the checks the recipe passed. */
  checks?: string[];
  /** Design-mock only: plain history lines. */
  history?: string[];
}

export interface KnowledgeVersion {
  id: number;
  number: number;
  status: "draft" | "published" | "archived";
  changes: number;
  summary: { added: number; changed: number; removed: number; note: string };
}

export interface KnowledgeListResponse {
  version: KnowledgeVersion | null;
  entries: KnowledgeEntry[];
  counts: Record<string, number>;
  needs_review: number;
}

export interface KnowledgeDetailResponse {
  entry: KnowledgeEntry;
  version: KnowledgeVersion | null;
  history: KnowledgeHistoryItem[];
}
