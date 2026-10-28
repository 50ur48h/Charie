import type { AnswerBlock } from "./chat-types";
import {
  emptyThinking,
  updateThinking,
  type ThinkingLine,
  type ThinkingState,
  type ThinkingSummary,
} from "../answer/thinking";

// Transient state for one live answer (architecture 09, "The live
// stream"). Only the block index selects the text buffer; text blocks
// arrive empty and fill with deltas. Unknown events and unparsable data
// are ignored with a diagnostic, never crash the feed.
export interface FeedChoice {
  text: string;
  options: { id: string; label: string }[];
}

export interface FeedError {
  code: string;
  message: string;
}

export interface FeedDone {
  message_id: number;
  status: string;
}

export interface FeedState {
  thinking: ThinkingState;
  blocks: AnswerBlock[];
  texts: Record<number, string>;
  choice: FeedChoice | null;
  error: FeedError | null;
  done: FeedDone | null;
  seenIds: Set<string>;
}

export function emptyFeed(): FeedState {
  return {
    thinking: emptyThinking(),
    blocks: [],
    texts: {},
    choice: null,
    error: null,
    done: null,
    seenIds: new Set<string>(),
  };
}

export interface FeedEvent {
  id: string | null;
  event: string;
  data: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function warn(reason: string, event: FeedEvent): void {
  console.warn(`Ignoring stream event (${reason}):`, event.event);
}

export function applyFeedEvent(state: FeedState, event: FeedEvent): FeedState {
  // Duplicate delivery (reconnect replays) applies once.
  if (event.id !== null) {
    if (state.seenIds.has(event.id)) return state;
  }
  const seenIds = new Set(state.seenIds);
  if (event.id !== null) seenIds.add(event.id);
  const seen = { ...state, seenIds };

  switch (event.event) {
    case "thinking": {
      if (!isRecord(event.data)) {
        warn("bad thinking data", event);
        return seen;
      }
      const line = event.data as unknown as ThinkingLine;
      if (typeof line.seq !== "number" || typeof line.title !== "string") {
        warn("bad thinking line", event);
        return seen;
      }
      return { ...seen, thinking: updateThinking(seen.thinking, { type: "line", line }) };
    }
    case "summary": {
      if (!isRecord(event.data)) {
        warn("bad summary data", event);
        return seen;
      }
      return {
        ...seen,
        thinking: updateThinking(seen.thinking, {
          type: "summary",
          summary: event.data as unknown as ThinkingSummary,
        }),
      };
    }
    case "block": {
      if (!isRecord(event.data) || typeof event.data.index !== "number") {
        warn("bad block data", event);
        return seen;
      }
      const block = event.data.block as AnswerBlock;
      if (!isRecord(block) || typeof block.type !== "string") {
        warn("bad block shape", event);
        return seen;
      }
      const blocks = seen.blocks.slice();
      blocks[event.data.index as number] = block;
      return { ...seen, blocks };
    }
    case "text": {
      if (!isRecord(event.data) || typeof event.data.index !== "number") {
        warn("bad text data", event);
        return seen;
      }
      const delta = event.data.delta;
      const chunk = typeof delta === "string" ? delta : "";
      if (typeof delta !== "string") warn("non-string delta", event);
      const index = event.data.index as number;
      return { ...seen, texts: { ...seen.texts, [index]: (seen.texts[index] ?? "") + chunk } };
    }
    case "choice": {
      if (!isRecord(event.data) || typeof event.data.text !== "string") {
        warn("bad choice data", event);
        return seen;
      }
      const options = Array.isArray(event.data.options)
        ? (event.data.options as unknown[]).filter(
            (o): o is { id: string; label: string } =>
              isRecord(o) && typeof o.id === "string" && typeof o.label === "string",
          )
        : [];
      return {
        ...seen,
        choice: { text: event.data.text as string, options },
      };
    }
    case "error": {
      if (!isRecord(event.data) || typeof event.data.message !== "string") {
        warn("bad error data", event);
        return seen;
      }
      return {
        ...seen,
        error: {
          code: typeof event.data.code === "string" ? (event.data.code as string) : "unknown",
          message: event.data.message as string,
        },
      };
    }
    case "done": {
      // Terminal: the first done wins; later ones (replay tails) change nothing.
      if (seen.done !== null) return seen;
      if (!isRecord(event.data) || typeof event.data.message_id !== "number") {
        warn("bad done data", event);
        return seen;
      }
      return {
        ...seen,
        done: {
          message_id: event.data.message_id as number,
          status: typeof event.data.status === "string" ? (event.data.status as string) : "",
        },
      };
    }
    default:
      warn("unknown event", event);
      return seen;
  }
}
