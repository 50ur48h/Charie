import { http, HttpResponse } from "msw";
import { readSavedTheme } from "../theme/theme";
import {
  addMockMessage,
  countMockPosts,
  createMockChat,
  finishMockMessage,
  getMockChat,
  listMockChats,
  deleteMockChat,
  renameMockChat,
} from "./sampleChat";
import {
  answerMockQuestion,
  listMockQuestions,
  skipMockQuestion,
  waitingMockCount,
  waitingOverride,
} from "./sampleQuestions";
import {
  currentMonth,
  isUsageMonth,
  mockSpending,
  mockUsage,
} from "./sampleUsage";
import {
  KNOWLEDGE_VERSION,
  getMockKnowledge,
  listMockKnowledge,
  suggestMockChange,
} from "./sampleKnowledge";
import { getMockPassword, setMockPassword } from "./password";
import { getMockSettings, updateMockSettings } from "./sampleSettings";
import { clearMockMemories, deleteMockMemory, listMockMemories } from "./sampleMemories";
import { openMockStream } from "./chat-stream";
import { needSession, SESSION_KEY } from "./session";
import { learnerHandlers } from "./learner/handlers";

export { SESSION_KEY };

export const CHATS_URL = "*/api/chats";
export const CHAT_DETAIL_URL = "*/api/chats/:id";
export const CHAT_MESSAGES_URL = "*/api/chats/:id/messages";
export const STATUS_URL = "*/api/status";
export const MESSAGE_FINISH_URL = "*/api/messages/:id/finish";
export const MESSAGE_STREAM_URL = "*/api/messages/:id/stream";
export const MESSAGE_FEEDBACK_URL = "*/api/messages/:id/feedback";
export const MESSAGE_WRONG_URL = "*/api/messages/:id/wrong";
export const QUESTIONS_URL = "*/api/questions";
export const QUESTION_ANSWER_URL = "*/api/questions/:id/answer";
export const QUESTION_SKIP_URL = "*/api/questions/:id/skip";
export const KNOWLEDGE_URL = "*/api/knowledge";
export const KNOWLEDGE_ENTRY_URL = "*/api/knowledge/:key";
export const KNOWLEDGE_SUGGEST_URL = "*/api/knowledge/:key/suggest";
export const USAGE_URL = "*/api/usage";
export const SETTINGS_URL = "*/api/settings";
export const ME_URL = "*/api/me";
export const HEALTH_URL = "*/api/health";
export const LOGIN_URL = "*/api/login";
export const LOGOUT_URL = "*/api/logout";
export const PASSWORD_URL = "*/api/password";
export const MEMORIES_URL = "*/api/memories";
export const MEMORY_DETAIL_URL = "*/api/memories/:id";
export const CATCH_ALL_URL = "*/api/*";

const TRIES_KEY = "charie-mock-tries";
const MAX_TRIES = 5;
const WINDOW_MS = 5 * 60 * 1000;

function readTries(): number[] {
  try {
    const raw = localStorage.getItem(TRIES_KEY);
    if (!raw) return [];
    const tries = JSON.parse(raw) as unknown;
    if (!Array.isArray(tries)) return [];
    return tries.filter((t): t is number => typeof t === "number");
  } catch {
    return [];
  }
}

function recentTries(now: number): number[] {
  return readTries().filter((t) => now - t < WINDOW_MS);
}

function recordTry(now: number): void {
  try {
    localStorage.setItem(TRIES_KEY, JSON.stringify([...recentTries(now), now]));
  } catch {
    // Private browsing: the try limit just doesn't stick.
  }
}

function clearTries(): void {
  try {
    localStorage.removeItem(TRIES_KEY);
  } catch {
    // Nothing to clear.
  }
}

function startSession(): void {
  try {
    localStorage.setItem(SESSION_KEY, "1");
  } catch {
    // Private browsing: the session just doesn't stick.
  }
}

function endSession(): void {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch {
    // Nothing to end.
  }
}

// Test-only delay (milliseconds in localStorage "charie-mock-delay-ms"), so
// browser tests can hold a chat-detail response back and prove the page stays
// locked while it refreshes. Meaningless outside mock mode.
async function mockDelay(): Promise<void> {
  try {
    const ms = Number(localStorage.getItem("charie-mock-delay-ms") ?? "0");
    if (ms > 0) await new Promise((resolve) => setTimeout(resolve, ms));
  } catch {
    // No delay without storage.
  }
}

export const handlers = [
  ...learnerHandlers,
  http.get(HEALTH_URL, () => HttpResponse.json({ ok: true })),
  http.post(LOGIN_URL, async ({ request }) => {
    const now = Date.now();
    if (recentTries(now).length >= MAX_TRIES) {
      return HttpResponse.json(
        { error: "too_many_tries", message: "Too many tries. Please wait 5 minutes, then try again." },
        { status: 429 },
      );
    }
    let password: unknown;
    try {
      password = ((await request.json()) as { password?: unknown }).password;
    } catch {
      password = undefined;
    }
    if (password !== getMockPassword()) {
      recordTry(now);
      return HttpResponse.json(
        { error: "wrong_password", message: "That password didn't work. Try again." },
        { status: 401 },
      );
    }
    clearTries();
    startSession();
    return HttpResponse.json({ ok: true });
  }),
  http.post(LOGOUT_URL, () => {
    endSession();
    return HttpResponse.json({ ok: true });
  }),
  http.get(ME_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json({
      logged_in: true,
      setup_done: true,
      theme: readSavedTheme(),
      chat_url: "http://localhost:5173",
      learner_url: "http://localhost:5174",
    });
  }),
  http.get(CHATS_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(listMockChats());
  }),
  http.get(QUESTIONS_URL, ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const status = new URL(request.url).searchParams.get("status");
    if (status !== null && status !== "waiting" && status !== "answered" && status !== "skipped") {
      return HttpResponse.json(
        { error: "bad_status", message: "Status must be waiting, answered or skipped." },
        { status: 400 },
      );
    }
    return HttpResponse.json({ questions: listMockQuestions(status ?? undefined) });
  }),
  http.post(QUESTION_ANSWER_URL, async ({ params, request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      body = undefined;
    }
    const record = (body ?? {}) as { option_id?: unknown; text?: unknown };
    const hasOption = typeof record.option_id === "string" && record.option_id !== "";
    const hasText = typeof record.text === "string" && record.text.trim() !== "";
    if (hasOption === hasText) {
      return HttpResponse.json(
        { error: "bad_answer", message: "Send exactly one of option_id or text." },
        { status: 400 },
      );
    }
    const outcome = hasOption
      ? answerMockQuestion(Number(params.id), { optionId: record.option_id as string })
      : answerMockQuestion(Number(params.id), { text: (record.text as string).trim() });
    if (outcome === "not_found") {
      return HttpResponse.json(
        { error: "not_found", message: "That question is gone." },
        { status: 404 },
      );
    }
    if (outcome === "bad_answer") {
      return HttpResponse.json(
        { error: "bad_answer", message: "That answer does not fit this question." },
        { status: 400 },
      );
    }
    return HttpResponse.json({ ok: true });
  }),
  http.post(QUESTION_SKIP_URL, ({ params }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    if (skipMockQuestion(Number(params.id)) === "not_found") {
      return HttpResponse.json(
        { error: "not_found", message: "That question is gone." },
        { status: 404 },
      );
    }
    return HttpResponse.json({ ok: true });
  }),
  http.get(KNOWLEDGE_URL, ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const url = new URL(request.url);
    const kind = url.searchParams.get("kind") ?? undefined;
    const q = url.searchParams.get("q") ?? undefined;
    return HttpResponse.json({
      entries: listMockKnowledge({ kind, q }),
      version: KNOWLEDGE_VERSION,
      status: "published",
    });
  }),
  http.get(KNOWLEDGE_ENTRY_URL, ({ params }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const entry = getMockKnowledge(String(params.key));
    if (entry === undefined) {
      return HttpResponse.json(
        { error: "not_found", message: "No entry has that key." },
        { status: 404 },
      );
    }
    return HttpResponse.json(entry);
  }),
  http.post(KNOWLEDGE_SUGGEST_URL, async ({ params, request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    let text: unknown;
    try {
      text = ((await request.json()) as { text?: unknown }).text;
    } catch {
      text = undefined;
    }
    if (typeof text !== "string" || text.trim() === "") {
      return HttpResponse.json(
        { error: "empty_text", message: "Write your suggestion first." },
        { status: 400 },
      );
    }
    const outcome = suggestMockChange(String(params.key), text.trim());
    if (outcome === "not_found") {
      return HttpResponse.json(
        { error: "not_found", message: "No entry has that key." },
        { status: 404 },
      );
    }
    return HttpResponse.json({ ok: true });
  }),
  http.get(USAGE_URL, ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const month = new URL(request.url).searchParams.get("month") ?? currentMonth();
    if (!isUsageMonth(month)) {
      return HttpResponse.json(
        { error: "bad_month", message: "Use a month like 2025-10." },
        { status: 400 },
      );
    }
    return HttpResponse.json(mockUsage(month));
  }),
  http.get(SETTINGS_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(getMockSettings());
  }),
  http.post(PASSWORD_URL, async ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      body = undefined;
    }
    const record = (body ?? {}) as { current?: unknown; new?: unknown };
    if (record.current !== getMockPassword()) {
      return HttpResponse.json(
        { error: "wrong_password", message: "The current password isn't right." },
        { status: 400 },
      );
    }
    if (typeof record.new !== "string" || record.new.length < 8) {
      return HttpResponse.json(
        { error: "password_too_short", message: "The new password needs at least 8 characters." },
        { status: 400 },
      );
    }
    setMockPassword(record.new);
    return HttpResponse.json({ ok: true });
  }),
  http.get(MEMORIES_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(listMockMemories());
  }),
  http.delete(MEMORY_DETAIL_URL, ({ params }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    if (!deleteMockMemory(Number(params.id))) {
      return HttpResponse.json(
        { error: "not_found", message: "That memory is gone." },
        { status: 404 },
      );
    }
    return HttpResponse.json({ ok: true });
  }),
  http.delete(MEMORIES_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    clearMockMemories();
    return HttpResponse.json({ ok: true });
  }),
  http.patch(SETTINGS_URL, async ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      body = undefined;
    }
    const record = (body ?? {}) as Record<string, unknown>;
    const outcome = updateMockSettings(record);
    if ("error" in outcome) {
      return HttpResponse.json(
        { error: outcome.error, message: outcome.message },
        { status: 400 },
      );
    }
    return HttpResponse.json(getMockSettings());
  }),
  http.post(CHATS_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(createMockChat(), { status: 201 });
  }),
  http.patch(CHAT_DETAIL_URL, async ({ params, request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    let title: unknown;
    try {
      title = ((await request.json()) as { title?: unknown }).title;
    } catch {
      title = undefined;
    }
    if (typeof title !== "string" || title.trim() === "") {
      return HttpResponse.json(
        { error: "empty_title", message: "Give the chat a title." },
        { status: 400 },
      );
    }
    if (renameMockChat(Number(params.id), title.trim()) === "not_found") {
      return HttpResponse.json(
        { error: "not_found", message: "That chat is gone." },
        { status: 404 },
      );
    }
    const chat = getMockChat(Number(params.id));
    return HttpResponse.json({
      id: chat?.id ?? Number(params.id),
      title: title.trim(),
      created_at: chat?.created_at ?? new Date().toISOString(),
      updated_at: chat?.updated_at ?? new Date().toISOString(),
    });
  }),
  http.delete(CHAT_DETAIL_URL, ({ params }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const outcome = deleteMockChat(Number(params.id));
    if (outcome === "not_found") {
      return HttpResponse.json(
        { error: "not_found", message: "That chat is gone." },
        { status: 404 },
      );
    }
    if (outcome === "running") {
      return HttpResponse.json(
        { error: "chat_running", message: "That answer is still running. Wait for it to finish, then delete." },
        { status: 409 },
      );
    }
    return HttpResponse.json({ ok: true });
  }),
  http.get(CHAT_DETAIL_URL, async ({ params }) => {
    await mockDelay();
    const blocked = needSession();
    if (blocked) return blocked;
    const chat = getMockChat(Number(params.id));
    if (chat === undefined) {
      return HttpResponse.json(
        { error: "not_found", message: "That chat is gone." },
        { status: 404 },
      );
    }
    return HttpResponse.json(chat);
  }),
  http.post(CHAT_MESSAGES_URL, async ({ params, request }) => {
    // At 100% the mock blocks new questions with the API shape.
    if (mockSpending(41.2).state === "paused") {
      return HttpResponse.json(
        {
          error: "spending_paused",
          message: "Questions are paused: this month\u2019s credit is used up. Raise the limit to keep asking.",
        },
        { status: 409 },
      );
    }
    const blocked = needSession();
    if (blocked) return blocked;
    let text: unknown;
    try {
      text = ((await request.json()) as { text?: unknown }).text;
    } catch {
      text = undefined;
    }
    if (typeof text !== "string" || text.trim() === "") {
      return HttpResponse.json(
        { error: "empty_text", message: "Please write a question first." },
        { status: 400 },
      );
    }
    countMockPosts("messages");
    const sent = addMockMessage(Number(params.id), text.trim());
    if (sent === undefined) {
      return HttpResponse.json(
        { error: "not_found", message: "That chat is gone." },
        { status: 404 },
      );
    }
    return HttpResponse.json(sent, { status: 201 });
  }),
  http.get(STATUS_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    const demoSpending = mockSpending(41.2);
    return HttpResponse.json({
      questions_waiting: waitingOverride() ?? waitingMockCount(),
      data_through: "2025-10-26",
      spending: demoSpending,
    });
  }),
  http.post(MESSAGE_FINISH_URL, ({ params }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    countMockPosts("finish");
    if (!finishMockMessage(Number(params.id))) {
      return HttpResponse.json(
        { error: "not_found", message: "We couldn't find that message." },
        { status: 404 },
      );
    }
    return HttpResponse.json({ ok: true });
  }),
  http.get(MESSAGE_STREAM_URL, ({ params, request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    const stream = openMockStream(
      Number(params.id),
      request.headers.get("Last-Event-ID"),
      request.signal,
    );
    if (stream === null) {
      return HttpResponse.json(
        { error: "not_found", message: "We couldn't find that message." },
        { status: 404 },
      );
    }
    return new HttpResponse(stream, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }),
  http.post(MESSAGE_FEEDBACK_URL, async ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    let vote: unknown;
    try {
      vote = ((await request.json()) as { vote?: unknown }).vote;
    } catch {
      vote = undefined;
    }
    if (vote !== "up" && vote !== "down" && vote !== null) {
      return HttpResponse.json(
        { error: "bad_vote", message: "Vote up, down or clear it." },
        { status: 400 },
      );
    }
    countMockPosts("feedback");
    return HttpResponse.json({ ok: true });
  }),
  http.post(MESSAGE_WRONG_URL, async ({ request }) => {
    const blocked = needSession();
    if (blocked) return blocked;
    let correction: unknown;
    try {
      correction = ((await request.json()) as { correction?: unknown }).correction;
    } catch {
      correction = undefined;
    }
    if (typeof correction !== "string" || correction.trim() === "") {
      return HttpResponse.json(
        { error: "empty_correction", message: "Please describe what is wrong." },
        { status: 400 },
      );
    }
    countMockPosts("wrong");
    // The learner to-do list itself ships later: the mock only proves the
    // correction was sent once and kept verbatim.
    return HttpResponse.json({ ok: true });
  }),
  http.all(CATCH_ALL_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(
      { error: "not_mocked", message: "The sample data doesn't cover this yet." },
      { status: 501 },
    );
  }),
];
