// Sample chat detail for the fake API: one finished answer covering every
// answer-block variant, plus fresh/thinking/finished seed states and a tiny
// store for chats the owner creates. The store is saved to localStorage so a
// page reload keeps created chats, messages and Finish now state (mock only,
// mirroring the session key). Sample data lives only here, never in the
// production bundle.
import type {
  Answer,
  AssistantMessage,
  Chat,
  UserMessage,
} from "../api/chat-types";
import type { ChatSummary } from "../api/types";
import summaries from "./data";
import {
  failedThinking,
  finishedSummary,
  finishedThinking,
  runningThinking,
  secondSummary,
  secondThinking,
} from "./sampleThinking";

export function sampleAnswer(messageId: number): Answer {
  return {
    message_id: messageId,
    kb_version: 14,
    data_through: "2025-10-26",
    blocks: [
      {
        type: "reading",
        text: "I read this as **net sales, orders and average order** for **1–26 Oct 2025**, compared with **1–30 Sep 2025**.",
      },
      {
        type: "text",
        paragraphs: [
          {
            sentences: [
              {
                kind: "fact",
                text: "October is a good month so far: net sales were <good>up 6.2%</good> at **$1.42M**.",
              },
              {
                kind: "possible_reason",
                text: "A likely reason is the holiday menu, which started on 1 Oct.",
              },
            ],
          },
          {
            sentences: [
              { kind: "conclusion", text: "We are ahead of September on every measure." },
              { kind: "suggestion", text: "Keep the holiday menu through November." },
              {
                kind: "note",
                text: "October only runs to the <mark>26th</mark> so far.",
              },
            ],
          },
        ],
      },
      {
        type: "kpis",
        items: [
          {
            label: "Net sales",
            value: "$1.42M",
            change: "+6.2%",
            direction: "up",
            compare: "vs Sep",
            spark: { values: [41200, 43800, 44100], unit: "money", currency: "USD" },
          },
          {
            label: "Delivery complaints",
            value: "18",
            change: "+5",
            direction: "down",
            compare: "vs Sep",
          },
          {
            label: "Refund rate",
            value: "2.1%",
            change: "−0.4%",
            direction: "down",
            compare: "vs Sep",
          },
          { label: "New guests", value: "12.4K" },
        ],
      },
      {
        type: "chart",
        kind: "bar_diverging",
        title: "Sales change by restaurant",
        subtitle: "Oct vs Sep 2025",
        x: "restaurant",
        y: "change",
        unit: "percent",
        highlight: ["Downtown"],
        data: {
          columns: ["restaurant", "change"],
          rows: [
            ["Downtown", { v: -18.2, f: "−18.2%" }],
            ["Uptown", { v: 9.4, f: "+9.4%" }],
          ],
        },
      },
      {
        type: "chart",
        kind: "line",
        title: "Delivery orders per day",
        subtitle: "1-7 Oct 2025",
        x: "day",
        y: "orders",
        unit: "count",
        data: {
          columns: ["day", "orders"],
          rows: [
            ["1 Oct", { v: 301, f: "301" }],
            ["2 Oct", { v: 287, f: "287" }],
            ["3 Oct", { v: 224, f: "224" }],
            ["4 Oct", { v: 342, f: "342" }],
            ["5 Oct", { v: 358, f: "358" }],
            ["6 Oct", { v: 295, f: "295" }],
            ["7 Oct", { v: 310, f: "310" }],
          ],
        },
      },
      {
        type: "table",
        title: "Top restaurants",
        columns: [
          { key: "restaurant", label: "Restaurant" },
          { key: "sales", label: "Net sales", unit: "money" },
        ],
        rows: [
          { restaurant: "Uptown", sales: { v: 96200, f: "$96.2K" } },
          { restaurant: "Downtown", sales: { v: 78400, f: "$78.4K" } },
        ],
      },
      {
        type: "tree",
        title: "Where the drop came from",
        nodes: [
          { id: "a", parent: null, label: "Net sales down $21.4K", tone: "bad" },
          { id: "b", parent: "a", label: "Delivery orders down $17.2K", tone: "bad" },
        ],
      },
      { type: "callout", tone: "note", text: "October has data up to the 26th only." },
      {
        type: "suggestions",
        title: "What I'd do",
        items: [
          {
            text: "Ask the delivery partner to check Downtown.",
            confidence: "likely",
          },
        ],
      },
      {
        type: "method",
        definitions: ["Net sales leave out refunds."],
        steps: ["Added up sales by restaurant for October and September."],
        queries: [{ purpose: "Monthly sales by restaurant", sql: "SELECT …" }],
        sources: [
          { document: "Incident log.docx", quote: "…", location: "page 2" },
        ],
      },
      {
        type: "follow_ups",
        items: ["How much did the outage cost us?", "Same for last year?"],
      },
    ],
  };
}

function finishedSeed(summary: ChatSummary): Chat {
  const started = summary.created_at;
  const firstUser: UserMessage = {
    id: 1,
    role: "user",
    text: "How are we doing this month?",
    status: "done",
    started_at: started,
  };
  const firstAssistant: AssistantMessage = {
    id: 2,
    role: "assistant",
    status: "done",
    mode: "thinking",
    answer: sampleAnswer(2),
    thinking: finishedThinking,
    summary: finishedSummary,
  };
  const secondUser: UserMessage = {
    id: 7,
    role: "user",
    text: "Same for last year?",
    status: "done",
    started_at: started,
  };
  const secondAssistant: AssistantMessage = {
    id: 8,
    role: "assistant",
    status: "done",
    mode: "thinking",
    answer: null,
    thinking: secondThinking,
    summary: secondSummary,
  };
  return {
    ...summary,
    messages: [firstUser, firstAssistant, secondUser, secondAssistant],
  };
}

function thinkingSeed(summary: ChatSummary): Chat {
  return {
    ...summary,
    messages: [
      {
        id: 3,
        role: "user",
        text: "Which dishes make us the most profit?",
        status: "done",
        started_at: summary.created_at,
      },
      {
        id: 4,
        role: "assistant",
        status: "thinking",
        mode: "thinking",
        answer: null,
        thinking: runningThinking,
        summary: null,
      },
    ],
  };
}

function failedSeed(summary: ChatSummary): Chat {
  return {
    ...summary,
    messages: [
      {
        id: 5,
        role: "user",
        text: "Weekend vs weekday sales",
        status: "done",
        started_at: summary.created_at,
      },
      {
        id: 6,
        role: "assistant",
        status: "failed",
        mode: "thinking",
        answer: null,
        thinking: failedThinking,
        summary: null,
      },
    ],
  };
}

const STORE_KEY = "charie-mock-chats";
const COUNT_MESSAGES_KEY = "charie-mock-count-messages";
const COUNT_FINISH_KEY = "charie-mock-count-finish";

let nextChatId = 100;
let nextMessageId = 1000;
let created = new Map<number, Chat>();
let rehydrated = false;
// Assistant messages with a genuinely running answer: created by POST and
// not yet finished or saved. Static seed fixtures never enter this set, so
// the fake stream can tell a live answer (full script) from an idle one
// (immediate done) without the production lifecycle knowing about fixtures.
let running = new Set<number>();
// Seed or created chats the owner deleted (mock only): list and detail hide
// them without touching the fixtures.
let deleted = new Set<number>();

function storage(): Storage | null {
  try {
    return localStorage;
  } catch {
    return null;
  }
}

function persist(): void {
  const store = storage();
  if (store === null) return;
  try {
    store.setItem(
      STORE_KEY,
      JSON.stringify({
        nextChatId,
        nextMessageId,
        created: [...created.values()],
        running: [...running],
      deleted: [...deleted],
      }),
    );
  } catch {
    // Private browsing: created chats just don't survive a reload.
  }
}

function rehydrate(): void {
  if (rehydrated) return;
  rehydrated = true;
  const store = storage();
  if (store === null) return;
  try {
    const raw = store.getItem(STORE_KEY);
    if (!raw) return;
    const data = JSON.parse(raw) as {
      nextChatId?: unknown;
      nextMessageId?: unknown;
      created?: unknown;
      running?: unknown;
    };
    if (
      typeof data.nextChatId !== "number" ||
      typeof data.nextMessageId !== "number" ||
      !Array.isArray(data.created)
    ) {
      return;
    }
    nextChatId = data.nextChatId;
    nextMessageId = data.nextMessageId;
    // Older stores predate the running and deleted sets.
    if (Array.isArray((data as { deleted?: unknown }).deleted)) {
      for (const id of (data as { deleted: unknown }).deleted as unknown[]) {
        if (typeof id === "number") deleted.add(id);
      }
    }
    if (Array.isArray(data.running)) {
      for (const id of data.running) {
        if (typeof id === "number") running.add(id);
      }
    }
    for (const chat of data.created) {
      if (
        typeof chat === "object" &&
        chat !== null &&
        typeof (chat as Chat).id === "number" &&
        Array.isArray((chat as Chat).messages)
      ) {
        const stored = chat as Chat;
        for (const message of stored.messages) {
          if (message.role !== "assistant") continue;
          const raw = message as unknown as Record<string, unknown>;
          if (!Array.isArray(raw.thinking)) message.thinking = [];
          if (raw.summary === undefined) message.summary = null;
          if (raw.answer === undefined) message.answer = null;
        }
        created.set(stored.id, stored);
      }
    }
  } catch {
    // A corrupt store starts fresh.
  }
}

// Test-only request counts, so browser tests can prove a double click sent
// one request. Meaningless outside mock mode.
export type MockPostKind = "messages" | "finish" | "feedback" | "wrong";

const COUNT_KEYS: Record<MockPostKind, string> = {
  messages: COUNT_MESSAGES_KEY,
  finish: COUNT_FINISH_KEY,
  feedback: "charie-mock-count-feedback",
  wrong: "charie-mock-count-wrong",
};

export function countMockPosts(kind: MockPostKind): void {
  const store = storage();
  if (store === null) return;
  try {
    const key = COUNT_KEYS[kind];
    store.setItem(key, String(Number(store.getItem(key) ?? "0") + 1));
  } catch {
    // Counts are test-only; ignore.
  }
}

// Drops the in-memory store but keeps the saved one, so tests can simulate a
// page reload without one. Browser tests get a real reload instead.
export function forgetMockChats(): void {
  rehydrated = false;
  nextChatId = 100;
  nextMessageId = 1000;
  created = new Map();
  running = new Set();
  deleted = new Set();
  rehydrate();
}

function seedDetail(summary: ChatSummary): Chat {
  if (summary.id === 1) return finishedSeed(summary);
  if (summary.id === 2) return thinkingSeed(summary);
  if (summary.id === 4) return failedSeed(summary);
  return { ...summary, messages: [] };
}

export function getMockChat(id: number): Chat | undefined {
  rehydrate();
  if (deleted.has(id)) return undefined;
  const made = created.get(id);
  if (made) return made;
  const summary = summaries.find((chat) => chat.id === id);
  return summary === undefined ? undefined : seedDetail(summary);
}

export function listMockChats(): ChatSummary[] {
  rehydrate();
  // A stored chat (created or touched by a POST) replaces its seed row.
  // Deleted chats stay gone (seeds are fixtures; the set hides them).
  const storedIds = new Set(created.keys());
  const made: ChatSummary[] = [...created.values()].map(
    ({ id, title, created_at, updated_at }) => ({ id, title, created_at, updated_at }),
  );
  return [...made, ...summaries.filter((summary) => !storedIds.has(summary.id))].filter((summary) => !deleted.has(summary.id));
}

export function createMockChat(): ChatSummary {
  rehydrate();
  const now = new Date().toISOString();
  const chat: Chat = {
    id: nextChatId,
    title: "New chat",
    created_at: now,
    updated_at: now,
    messages: [],
  };
  nextChatId += 1;
  created.set(chat.id, chat);
  persist();
  return {
    id: chat.id,
    title: chat.title,
    created_at: chat.created_at,
    updated_at: chat.updated_at,
  };
}

// Rename a stored or seed chat (mock only). Unknown ids stay unknown.
export function renameMockChat(chatId: number, title: string): "ok" | "not_found" {
  const chat = storedChat(chatId);
  if (chat === undefined) return "not_found";
  chat.title = title;
  chat.updated_at = new Date().toISOString();
  created.set(chat.id, chat);
  persist();
  return "ok";
}

// Delete a chat (mock only). A chat with a genuinely running answer refuses,
// mirroring the real API; seeds hide via the deleted set, fixtures untouched.
export function deleteMockChat(chatId: number): "ok" | "not_found" | "running" {
  rehydrate();
  if (deleted.has(chatId)) return "not_found";
  const existing = created.get(chatId);
  if (existing !== undefined) {
    if (existing.messages.some((message) => message.role === "assistant" && running.has(message.id))) return "running";
  } else {
    const summary = summaries.find((item) => item.id === chatId);
    if (summary === undefined) return "not_found";
    if (seedDetail(summary).messages.some((message) => message.role === "assistant" && running.has(message.id))) return "running";
  }
  created.delete(chatId);
  deleted.add(chatId);
  persist();
  return "ok";
}

function storedChat(chatId: number): Chat | undefined {
  rehydrate();
  if (deleted.has(chatId)) return undefined;
  const existing = created.get(chatId);
  if (existing) return existing;
  const summary = summaries.find((chat) => chat.id === chatId);
  if (summary === undefined) return undefined;
  const chat = seedDetail(summary);
  created.set(chatId, chat);
  persist();
  return chat;
}

export function finishMockMessage(messageId: number): "ok" | "done" | "not_found" {
  rehydrate();
  const chats: Chat[] = [...created.values()];
  for (const summary of summaries) {
    const chat = storedChat(summary.id);
    if (chat !== undefined && !chats.includes(chat)) chats.push(chat);
  }
  for (const chat of chats) {
    const message = chat.messages.find(
      (item) => item.id === messageId && item.role === "assistant",
    );
    if (message !== undefined && message.role === "assistant") {
      if (
        message.status === "done" ||
        message.status === "failed" ||
        message.status === "stopped"
      ) {
        return "done";
      }
      message.status = "stopped";
      running.delete(messageId);
      for (const line of message.thinking) {
        if (line.status === "running") line.status = "done";
      }
      created.set(chat.id, chat);
      persist();
      return "ok";
    }
  }
  return "not_found";
}

export function addMockMessage(
  chatId: number,
  text: string,
): { user_message_id: number; assistant_message_id: number } | undefined {
  const chat = storedChat(chatId);
  if (chat === undefined) return undefined;
  if (chat.messages.length === 0) {
    const cut = text.slice(0, 60);
    chat.title =
      text.length <= 60
        ? text
        : `${cut.lastIndexOf(" ") > 0 ? cut.slice(0, cut.lastIndexOf(" ")) : cut}…`;
  }
  const userId = nextMessageId;
  const assistantId = nextMessageId + 1;
  nextMessageId += 2;
  const now = new Date().toISOString();
  chat.messages.push(
    { id: userId, role: "user", text, status: "done", started_at: now },
    {
      id: assistantId,
      role: "assistant",
      status: "thinking",
      mode: "thinking",
      answer: null,
      thinking: [],
      summary: null,
    },
  );
  running.add(assistantId);
  created.set(chat.id, chat);
  persist();
  return { user_message_id: userId, assistant_message_id: assistantId };
}

// (Answer, AssistantMessage and Chat are already imported above.)
export interface MockAssistantRef {
  chat: Chat;
  index: number;
  message: AssistantMessage;
}

// Locate an assistant message across seed and created chats (same search
// pattern as finishMockMessage). Used by the fake stream to play and save
// a live answer for freshly sent messages.
// True while a chat has a genuinely running answer: sent and neither
// finished nor saved. Used by the ask handler to refuse a second question,
// like the real API.
export function isMockChatRunning(chatId: number): boolean {
  const chat = storedChat(chatId);
  if (chat === undefined) return false;
  return chat.messages.some(
    (message) => message.role === "assistant" && running.has(message.id),
  );
}

// True while an assistant message has a genuinely running answer: sent and
// neither finished nor saved. Static seeds never qualify, so the fake
// stream can serve them an immediate done without touching fixtures.
export function isMockMessageRunning(messageId: number): boolean {
  rehydrate();
  return running.has(messageId);
}

export function findMockAssistant(messageId: number): MockAssistantRef | undefined {
  rehydrate();
  const chats: Chat[] = [...created.values()];
  for (const summary of summaries) {
    const chat = storedChat(summary.id);
    if (chat !== undefined && !chats.includes(chat)) chats.push(chat);
  }
  for (const chat of chats) {
    const index = chat.messages.findIndex(
      (item) => item.id === messageId && item.role === "assistant",
    );
    if (index !== -1) {
      const message = chat.messages[index];
      if (message.role === "assistant") return { chat, index, message };
    }
  }
  return undefined;
}

// Save a streamed answer onto its message, unless Finish now stopped it
// first. Returns false when there is nothing to save into.
export function storeMockAnswer(
  messageId: number,
  answer: Answer,
  thinking: AssistantMessage["thinking"],
  summary: AssistantMessage["summary"],
): boolean {
  const ref = findMockAssistant(messageId);
  if (ref === undefined) return false;
  if (ref.message.status === "stopped") return false;
  ref.message.status = "done";
  running.delete(messageId);
  ref.message.answer = answer;
  ref.message.thinking = thinking;
  ref.message.summary = summary;
  created.set(ref.chat.id, ref.chat);
  persist();
  return true;
}

export function resetMockChats(): void {
  nextChatId = 100;
  nextMessageId = 1000;
  created = new Map();
  running = new Set();
  deleted = new Set();
  rehydrated = true;
  const store = storage();
  if (store === null) return;
  try {
    store.removeItem(STORE_KEY);
    store.removeItem(COUNT_MESSAGES_KEY);
    store.removeItem(COUNT_FINISH_KEY);
    store.removeItem(COUNT_KEYS.feedback);
    store.removeItem(COUNT_KEYS.wrong);
  } catch {
    // Nothing to clear.
  }
}
