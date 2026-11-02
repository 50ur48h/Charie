// Fake answer stream for mock mode (P03.7): GET /api/messages/{id}/stream.
// Each connection replays the message's scripted events after the
// client's Last-Event-ID, then keeps playing it live with small gaps so
// the UI visibly streams. Test faults come from localStorage
// "charie-mock-stream-fault": {"dropAfter": n} closes the first
// connection after n events (the reconnect replays the rest),
// {"stallAfter": n} hangs the first connection after n events (a reload
// resumes from scratch), {"errorCode", "errorMessage"} sends an error
// event, holds, then finishes normally. Connections are counted in
// "charie-mock-stream-opens". Messages with no running answer (static
// seeds, finished answers) get an immediate done: like the real back
// end, there is nothing live to stream for them.
import type { Answer } from "../api/chat-types";
import type { ThinkingLine, ThinkingSummary } from "../answer/thinking";
import {
  findMockAssistant,
  isMockMessageRunning,
  setPendingMockChoice,
  storeMockAnswer,
} from "./sampleChat";

const FAULT_KEY = "charie-mock-stream-fault";
const OPENS_KEY = "charie-mock-stream-opens";
const EVENT_GAP_MS = 70;
const ERROR_HOLD_MS = 500;

interface ScriptEvent {
  id: number;
  name: string;
  data: unknown;
  holdMs: number;
}

interface Script {
  events: ScriptEvent[];
  dropAfter: number | null;
  dropped: boolean;
  stallAfter: number | null;
  stalled: boolean;
  answer: Answer;
  thinking: ThinkingLine[];
  summary: ThinkingSummary;
}

const scripts = new Map<number, Script>();

interface StreamFault {
  dropAfter?: number;
  stallAfter?: number;
  errorCode?: string;
  errorMessage?: string;
}

function readFault(): StreamFault {
  try {
    const raw = localStorage.getItem(FAULT_KEY);
    if (!raw) return {};
    localStorage.removeItem(FAULT_KEY);
    const fault = JSON.parse(raw) as unknown;
    if (typeof fault !== "object" || fault === null) return {};
    return fault as StreamFault;
  } catch {
    return {};
  }
}

export function countStreamOpens(): number {
  try {
    const next = Number(localStorage.getItem(OPENS_KEY) ?? "0") + 1;
    localStorage.setItem(OPENS_KEY, String(next));
    return next;
  } catch {
    return 0;
  }
}

export function readStreamOpens(): number {
  try {
    return Number(localStorage.getItem(OPENS_KEY) ?? "0");
  } catch {
    return 0;
  }
}

const CHOICE_QUESTION = "Which are our best restaurants?";
const CHOICE_TEXT = "How should I rank them?";
const CHOICE_OPTIONS = [
  { id: "by_net_sales", label: "By net sales" },
  { id: "by_growth", label: "By growth" },
  { id: "by_average_order", label: "By average order" },
];

function buildChoiceScript(messageId: number): Script {
  const at = new Date().toISOString();
  const line1: ThinkingLine = { seq: 1, kind: "step", status: "done", title: "Reading your question", at };
  const line2: ThinkingLine = {
    seq: 2,
    kind: "decision",
    status: "done",
    title: "Asked you one quick question",
    body: "This can be read a few ways, so I'd rather ask than guess.",
    at,
  };
  const summary: ThinkingSummary = { seconds: 2, steps: 1, queries: 0, documents: 0 };
  const raw: { name: string; data: unknown; holdMs?: number }[] = [
    { name: "thinking", data: { ...line1, status: "running" } },
    { name: "thinking", data: line1 },
    { name: "thinking", data: line2 },
    { name: "choice", data: { text: CHOICE_TEXT, options: CHOICE_OPTIONS } },
    { name: "summary", data: summary },
    { name: "done", data: { message_id: messageId, status: "needs_choice" } },
  ];
  const events: ScriptEvent[] = raw.map((event, atIndex) => ({
    id: atIndex + 1,
    name: event.name,
    data: event.data,
    holdMs: event.holdMs ?? EVENT_GAP_MS,
  }));
  const answer: Answer = {
    message_id: messageId,
    kb_version: 14,
    data_through: "2025-10-26",
    blocks: [],
    choice: { text: CHOICE_TEXT, options: CHOICE_OPTIONS },
  };
  return {
    events,
    dropAfter: null,
    dropped: false,
    stallAfter: null,
    stalled: false,
    answer,
    thinking: [line1, line2],
    summary,
  };
}

function buildScript(messageId: number, question: string): Script {
  if (question === CHOICE_QUESTION) return buildChoiceScript(messageId);
  const at = new Date().toISOString();
  const line1: ThinkingLine = { seq: 1, kind: "step", status: "done", title: "Reading your question", at };
  const line2: ThinkingLine = {
    seq: 2,
    kind: "query",
    status: "done",
    title: "Adding up the numbers",
    details: { sql: "SELECT restaurant, SUM(net) FROM sales GROUP BY 1" },
    at,
  };
  const summary: ThinkingSummary = { seconds: 6, steps: 2, queries: 1, documents: 0 };
  const reading = `I read this as ${question}.`;
  const buffer = `${reading} The numbers are in and October is ahead.`;
  const chunks = ["I read this ", `as ${question}. `, "The numbers are in ", "and October is ahead. "];
  const raw: { name: string; data: unknown; holdMs?: number }[] = [
    { name: "thinking", data: { ...line1, status: "running" } },
    { name: "thinking", data: line1 },
    { name: "thinking", data: { ...line2, status: "running" } },
    { name: "block", data: { index: 0, block: { type: "text", paragraphs: [] } } },
    ...chunks.map((delta) => ({ name: "text", data: { index: 0, delta } })),
    { name: "thinking", data: line2 },
    { name: "summary", data: summary },
    { name: "done", data: { message_id: messageId, status: "done" } },
  ];
  const fault = readFault();
  if (fault.errorCode !== undefined) {
    raw.splice(3, 0, {
      name: "error",
      data: { code: fault.errorCode, message: fault.errorMessage ?? "Something went wrong on our side." },
      holdMs: ERROR_HOLD_MS,
    });
  }
  const events: ScriptEvent[] = raw.map((event, atIndex) => ({
    id: atIndex + 1,
    name: event.name,
    data: event.data,
    holdMs: event.holdMs ?? EVENT_GAP_MS,
  }));
  const sentences = buffer
    .split(/(?<=[.?!])\s+/)
    .map((text) => text.trim())
    .filter((text) => text !== "");
  const answer: Answer = {
    message_id: messageId,
    kb_version: 14,
    data_through: "2025-10-26",
    blocks: [
      { type: "reading", text: reading },
      {
        type: "text",
        paragraphs: [{ sentences: sentences.map((text) => ({ kind: "fact" as const, text })) }],
      },
    ],
  };
  return {
    events,
    dropAfter:
      fault.dropAfter !== undefined && fault.dropAfter < events.length ? fault.dropAfter : null,
    dropped: false,
    stallAfter:
      fault.stallAfter !== undefined && fault.stallAfter < events.length ? fault.stallAfter : null,
    stalled: false,
    answer,
    thinking: [line1, line2],
    summary,
  };
}

/**
 * One done event, then close: the message is not running, so there is
 * nothing to replay. Never saves: static fixtures stay exactly as served.
 */
function doneStream(messageId: number, signal: AbortSignal): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  const body = encoder.encode(
    `id: 0\nevent: done\ndata: ${JSON.stringify({ message_id: messageId, status: savedStatus(messageId) })}\n\n`,
  );
  let sent = false;
  return new ReadableStream<Uint8Array>({
    start(controller) {
      if (signal.aborted) {
        try {
          controller.close();
        } catch {
          // Already closed.
        }
        return;
      }
      const onAbort = (): void => {
        try {
          controller.close();
        } catch {
          // Already closed.
        }
      };
      signal.addEventListener("abort", onAbort, { once: true });
      if (!sent) {
        sent = true;
        controller.enqueue(body);
      }
      try {
        controller.close();
      } catch {
        // Already closed.
      }
    },
  });
}

/**
 * Open a fake SSE body for an assistant message. Null when the message
 * is unknown. The caller closes on abort; timers are cleaned up.
 */
function savedStatus(messageId: number): string {
  const ref = findMockAssistant(messageId);
  if (ref === undefined) return "done";
  return ref.message.status;
}

export function openMockStream(
  messageId: number,
  lastEventId: string | null,
  signal: AbortSignal,
): ReadableStream<Uint8Array> | null {
  const ref = findMockAssistant(messageId);
  if (ref === undefined) return null;
  countStreamOpens();
  if (!isMockMessageRunning(messageId)) return doneStream(messageId, signal);
  const before = ref.chat.messages[ref.index - 1];
  const question =
    before !== undefined && before.role === "user" ? before.text : "your question";
  const built = scripts.get(messageId) ?? buildScript(messageId, question);
  scripts.set(messageId, built);
  const script = built;
  if (script.answer.choice !== undefined) {
    setPendingMockChoice(ref.chat.id, { messageId, options: script.answer.choice.options });
  }
  let from = 0;
  if (lastEventId !== null) {
    const seen = Number(lastEventId);
    if (Number.isInteger(seen)) from = script.events.findIndex((event) => event.id > seen);
    if (from === -1) from = script.events.length;
  }
  // A drop fault fires once: the reconnect replays cleanly to done.
  const dropCount = script.dropped ? -1 : (script.dropAfter ?? -1);
  script.dropped = true;
  const encoder = new TextEncoder();
  let at = from < 0 ? 0 : from;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let closed = false;

  function finish(controller: ReadableStreamDefaultController<Uint8Array>): void {
    if (closed) return;
    closed = true;
    if (timer !== undefined) clearTimeout(timer);
    try {
      controller.close();
    } catch {
      // Already closed.
    }
  }

  return new ReadableStream<Uint8Array>({
    start(controller) {
      if (signal.aborted) {
        finish(controller);
        return;
      }
      const onAbort = (): void => finish(controller);
      signal.addEventListener("abort", onAbort, { once: true });
      function step(): void {
        if (closed || signal.aborted) {
          finish(controller);
          return;
        }
        if (at >= script.events.length) {
          storeMockAnswer(
            messageId,
            script.answer,
            script.thinking,
            script.summary,
            script.answer.choice === undefined ? "done" : "needs_choice",
          );
          finish(controller);
          return;
        }
        if (dropCount !== -1 && at >= dropCount) {
          finish(controller);
          return;
        }
        const event = script.events[at];
        at += 1;
        controller.enqueue(
          encoder.encode(`id: ${event.id}\nevent: ${event.name}\ndata: ${JSON.stringify(event.data)}\n\n`),
        );
        // A stall fault hangs the first connection after its events: only
        // an abort (or a reload, which resumes from scratch) ends it.
        if (!script.stalled && script.stallAfter !== null && at >= script.stallAfter) {
          script.stalled = true;
          return;
        }
        timer = setTimeout(step, event.holdMs);
      }
      step();
    },
    cancel() {
      closed = true;
      if (timer !== undefined) clearTimeout(timer);
    },
  });
}
