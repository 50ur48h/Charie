// Thinking-panel state (architecture 09, "The live stream"). A `running`
// line becomes `done` with the same `seq`. Kinds and details follow the P03.3
// plan: 09 names the event fields but not their values.
// P03.7 reuses `updateThinking` for the live stream.

export type ThinkingStatus = "running" | "done" | "failed";

export type ThinkingKind = "step" | "found" | "query" | "document" | "decision" | "check" | "note";

export interface ThinkingLineDetails {
  sql?: string;
  document?: string;
  quote?: string;
  location?: string;
  note?: string;
}

export interface ThinkingLine {
  seq: number;
  kind: ThinkingKind;
  status: ThinkingStatus;
  title: string;
  body?: string;
  details?: ThinkingLineDetails;
  at: string;
}

export interface ThinkingSummary {
  seconds: number;
  steps: number;
  queries: number;
  documents: number;
}

export interface ThinkingState {
  lines: ThinkingLine[];
  summary: ThinkingSummary | null;
}

export type ThinkingEvent =
  | { type: "line"; line: ThinkingLine }
  | { type: "summary"; summary: ThinkingSummary };

export function emptyThinking(): ThinkingState {
  return { lines: [], summary: null };
}

export function updateThinking(state: ThinkingState, event: ThinkingEvent): ThinkingState {
  if (event.type === "summary") {
    return { ...state, summary: event.summary };
  }
  const index = state.lines.findIndex((line) => line.seq === event.line.seq);
  if (index === -1) {
    return { ...state, lines: [...state.lines, event.line] };
  }
  return {
    ...state,
    lines: state.lines.map((line, at) => (at === index ? event.line : line)),
  };
}

export function formatSummary(summary: ThinkingSummary): string {
  const documents = summary.documents === 1 ? "1 document" : `${summary.documents} documents`;
  return `Thought for ${summary.seconds} seconds · ${summary.steps} steps · ${summary.queries} queries · ${documents}`;
}
