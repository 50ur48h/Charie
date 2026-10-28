// Knowledge entries (architecture 09 addresses, design knowledge.js).
// Shared by the chat read-only page and the learner editor (P04.8).
export type KnowledgeKind =
  | "number"
  | "word"
  | "table"
  | "rule"
  | "code"
  | "event"
  | "problem";

export type KnowledgeConfidence = "owner" | "data" | "doc" | "guess" | "conflict";

export interface KnowledgeSource {
  doc: string;
  quote?: string;
}

export interface KnowledgeEntry {
  /** Stable fixture key (for example "metric.net_sales"). Never a list index. */
  key: string;
  kind: KnowledgeKind;
  name: string;
  confidence: KnowledgeConfidence;
  used: number;
  short: string;
  meaning?: string;
  how?: string[];
  sql?: string;
  checks?: string[];
  sources?: KnowledgeSource[];
  history?: string[];
}

export interface KnowledgeListResponse {
  entries: KnowledgeEntry[];
  version: number | null;
  status: string | null;
}
