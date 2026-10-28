import { http, HttpResponse } from "msw";
import { readSavedTheme } from "../theme/theme";
import {
  addMockMessage,
  countMockPosts,
  createMockChat,
  finishMockMessage,
  getMockChat,
  listMockChats,
} from "./sampleChat";
import { SAMPLE_PASSWORD } from "./password";

export const CHATS_URL = "*/api/chats";
export const CHAT_DETAIL_URL = "*/api/chats/:id";
export const CHAT_MESSAGES_URL = "*/api/chats/:id/messages";
export const STATUS_URL = "*/api/status";
export const MESSAGE_FINISH_URL = "*/api/messages/:id/finish";
export const ME_URL = "*/api/me";
export const HEALTH_URL = "*/api/health";
export const LOGIN_URL = "*/api/login";
export const LOGOUT_URL = "*/api/logout";
export const CATCH_ALL_URL = "*/api/*";

export const SESSION_KEY = "charie-mock-session";
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

function hasSession(): boolean {
  try {
    return localStorage.getItem(SESSION_KEY) === "1";
  } catch {
    return false;
  }
}

const NOT_LOGGED_IN = {
  error: "not_logged_in",
  message: "Please sign in again.",
};

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

function needSession(): Response | null {
  if (hasSession()) return null;
  return HttpResponse.json(NOT_LOGGED_IN, { status: 401 });
}

export const handlers = [
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
    if (password !== SAMPLE_PASSWORD) {
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
    return HttpResponse.json({ logged_in: true, setup_done: true, theme: readSavedTheme() });
  }),
  http.get(CHATS_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(listMockChats());
  }),
  http.post(CHATS_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(createMockChat(), { status: 201 });
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
    return HttpResponse.json({ questions_waiting: 3, data_through: "2025-10-26" });
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
  http.all(CATCH_ALL_URL, () => {
    const blocked = needSession();
    if (blocked) return blocked;
    return HttpResponse.json(
      { error: "not_mocked", message: "The sample data doesn't cover this yet." },
      { status: 501 },
    );
  }),
];
