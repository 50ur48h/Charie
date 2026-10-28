// Chat, message and answer shapes (architecture 09, "The answer format").
// Phases 3-4 write these; the back end (Phases 5-10) must send exactly them.
import type { TreeNode } from "../charts/tree";
import type { ThinkingLine, ThinkingSummary } from "../answer/thinking";

export type MessageStatus =
  | "thinking"
  | "writing"
  | "done"
  | "stopped"
  | "failed"
  | "needs_choice";

export type MessageMode = "thinking" | "quick";

export type SentenceKind = "fact" | "conclusion" | "possible_reason" | "suggestion" | "note";

export interface CellValue {
  v: number;
  f: string;
}

export interface ReadingBlock {
  type: "reading";
  text: string;
}

export interface TextSentence {
  kind: SentenceKind;
  text: string;
}

export interface TextBlock {
  type: "text";
  paragraphs: { sentences: TextSentence[] }[];
}

export interface KpiSpark {
  values: number[];
  unit: string;
  currency?: string;
}

export interface KpiItem {
  label: string;
  value: string;
  change?: string;
  direction?: "up" | "down" | "flat";
  compare?: string;
  spark?: KpiSpark;
}

export interface KpisBlock {
  type: "kpis";
  items: KpiItem[];
}

export type Cell = string | number | CellValue | null;

export interface ChartBlock {
  type: "chart";
  kind: string;
  title: string;
  subtitle?: string;
  x: string;
  y: string;
  unit: string;
  currency?: string;
  highlight?: string[];
  data: { columns: string[]; rows: Cell[][] };
}

export interface TableColumn {
  key: string;
  label: string;
  unit?: string;
}

export interface TableBlock {
  type: "table";
  title: string;
  columns: TableColumn[];
  rows: Record<string, Cell>[];
}

export interface TreeBlock {
  type: "tree";
  title: string;
  nodes: TreeNode[];
}

export interface CalloutBlock {
  type: "callout";
  tone: string;
  text: string;
}

export interface SuggestionItem {
  text: string;
  confidence: string;
}

export interface SuggestionsBlock {
  type: "suggestions";
  title?: string;
  items: SuggestionItem[];
}

export interface MethodQuery {
  purpose: string;
  sql: string;
}

export interface MethodSource {
  document: string;
  quote: string;
  location: string;
}

export interface MethodBlock {
  type: "method";
  definitions: string[];
  steps: string[];
  queries: MethodQuery[];
  sources: MethodSource[];
}

export interface FollowUpsBlock {
  type: "follow_ups";
  items: string[];
}

export type AnswerBlock =
  | ReadingBlock
  | TextBlock
  | KpisBlock
  | ChartBlock
  | TableBlock
  | TreeBlock
  | CalloutBlock
  | SuggestionsBlock
  | MethodBlock
  | FollowUpsBlock;

export interface Answer {
  message_id: number;
  kb_version: number;
  data_through: string;
  blocks: AnswerBlock[];
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  answer?: Answer;
  status: MessageStatus;
  mode: MessageMode;
}

export interface Chat {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
  thinking: ThinkingLine[];
  thinking_summary: ThinkingSummary | null;
}
