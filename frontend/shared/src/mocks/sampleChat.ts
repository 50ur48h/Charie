// Sample chat detail for the fake API: one finished answer covering every
// answer-block variant, plus fresh/thinking/finished seed states and a tiny
// in-memory store for chats the owner creates. Sample data lives only here,
// never in the production bundle.
import type { Answer, Chat, ChatMessage } from "../api/chat-types";
import type { ChatSummary } from "../api/types";
import summaries from "./data";

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
              { kind: "note", text: "October has data up to the 26th only." },
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
  const user: ChatMessage = {
    id: 1,
    role: "user",
    text: "How are we doing this month?",
    status: "done",
    mode: "thinking",
  };
  const assistant: ChatMessage = {
    id: 2,
    role: "assistant",
    text: "",
    answer: sampleAnswer(2),
    status: "done",
    mode: "thinking",
  };
  return { ...summary, messages: [user, assistant] };
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
        mode: "thinking",
      },
      { id: 4, role: "assistant", text: "", status: "thinking", mode: "thinking" },
    ],
  };
}

let nextChatId = 100;
let nextMessageId = 1000;
const created = new Map<number, Chat>();

function seedDetail(summary: ChatSummary): Chat {
  if (summary.id === 1) return finishedSeed(summary);
  if (summary.id === 2) return thinkingSeed(summary);
  return { ...summary, messages: [] };
}

export function getMockChat(id: number): Chat | undefined {
  const made = created.get(id);
  if (made) return made;
  const summary = summaries.find((chat) => chat.id === id);
  return summary === undefined ? undefined : seedDetail(summary);
}

export function listMockChats(): ChatSummary[] {
  const made: ChatSummary[] = [...created.values()].map(
    ({ id, title, created_at, updated_at }) => ({ id, title, created_at, updated_at }),
  );
  return [...made, ...summaries];
}

export function createMockChat(): ChatSummary {
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
  return {
    id: chat.id,
    title: chat.title,
    created_at: chat.created_at,
    updated_at: chat.updated_at,
  };
}

export function addMockMessage(
  chatId: number,
  text: string,
): { user_message_id: number; assistant_message_id: number } | undefined {
  const chat = getMockChat(chatId);
  if (chat === undefined) return undefined;
  if (chat.messages.length === 0) {
    chat.title = text.length > 60 ? `${text.slice(0, 60)}…` : text;
  }
  const userId = nextMessageId;
  const assistantId = nextMessageId + 1;
  nextMessageId += 2;
  chat.messages.push(
    { id: userId, role: "user", text, status: "done", mode: "thinking" },
    { id: assistantId, role: "assistant", text: "", status: "thinking", mode: "thinking" },
  );
  created.set(chat.id, chat);
  return { user_message_id: userId, assistant_message_id: assistantId };
}

export function resetMockChats(): void {
  nextChatId = 100;
  nextMessageId = 1000;
  created.clear();
}
