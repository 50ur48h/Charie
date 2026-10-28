// Answer block shapes, re-exported from the chat contract in
// ../api/chat-types.ts (architecture 09, "The answer format"). The
// contract file stays the single source of truth; this barrel gives
// the answer components one local import.
export type {
  Answer,
  AnswerBlock,
  SuggestionItem,
  TextSentence,
} from "../api/chat-types";
