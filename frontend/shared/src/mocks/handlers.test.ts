import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "vitest";
import { setupServer } from "msw/node";
import { SESSION_KEY, handlers } from "./handlers";
import type { ChatSummary } from "../api/types";
import { resetMockChats } from "./sampleChat";
import { resetMockQuestions, waitingOverride } from "./sampleQuestions";
import { resetMockKnowledge, mockSuggestions } from "./sampleKnowledge";
import { resetMockUsage } from "./sampleUsage";

const server = setupServer(...handlers);

const APP = "https://charie.invalid";

beforeAll(() => {
  server.listen();
});

afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
});

beforeEach(() => {
  resetMockChats();
  resetMockQuestions();
  resetMockKnowledge();
  resetMockUsage();
});

afterAll(() => {
  server.close();
});

async function post(path: string, body: unknown): Promise<Response> {
  return fetch(`${APP}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function signIn(): Promise<void> {
  const response = await post("/api/login", { password: "bella-forno" });
  expect(response.status).toBe(200);
}

describe("mock handlers", () => {
  test("GET /api/chats gives the 8 sample chats, newest first", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/chats`);
    expect(response.status).toBe(200);
    const chats = (await response.json()) as ChatSummary[];
    expect(chats).toHaveLength(8);
    expect(chats.map((chat) => chat.title)).toEqual([
      "How are we doing this month?",
      "Top dishes by profit",
      "Why did delivery drop in Austin?",
      "Weekend vs weekday sales",
      "Coupon impact in September",
      "Food waste by restaurant",
      "Best hours to add staff",
      "Dallas vs Houston, last quarter",
    ]);
    const times = chats.map((chat) => Date.parse(chat.updated_at));
    expect([...times].sort((a, b) => b - a)).toEqual(times);
  });

  test("GET /api/me says you are logged in", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/me`);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ logged_in: true });
  });

  test("GET /api/health says ok", async () => {
    const response = await fetch(`${APP}/api/health`);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  test("an address without a fake answer gets 501 and a plain-English message", async () => {
    await signIn();
    const response = await post("/api/nothing-yet", {});
    expect(response.status).toBe(501);
    await expect(response.json()).resolves.toMatchObject({
      error: "not_mocked",
      message: "The sample data doesn't cover this yet.",
    });
  });

  test("the sample password starts a session", async () => {
    const response = await post("/api/login", { password: "bella-forno" });
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
    expect(localStorage.getItem(SESSION_KEY)).toBe("1");
  });

  test("a wrong password gets 401", async () => {
    const response = await post("/api/login", { password: "nope" });
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toMatchObject({ error: "wrong_password" });
    expect(localStorage.getItem(SESSION_KEY)).toBeNull();
  });

  test("after 5 wrong tries, the next try gets 429", async () => {
    for (let i = 0; i < 5; i += 1) {
      const response = await post("/api/login", { password: "nope" });
      expect(response.status).toBe(401);
    }
    const blocked = await post("/api/login", { password: "nope" });
    expect(blocked.status).toBe(429);
    await expect(blocked.json()).resolves.toMatchObject({ error: "too_many_tries" });
    const rightButBlocked = await post("/api/login", { password: "bella-forno" });
    expect(rightButBlocked.status).toBe(429);
  });

  test("GET /api/chats needs a session", async () => {
    const response = await fetch(`${APP}/api/chats`);
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toMatchObject({ error: "not_logged_in" });
  });

  test("POST /api/chats starts a new chat, then a question returns message ids", async () => {
    await signIn();
    const created = await post("/api/chats", {});
    expect(created.status).toBe(201);
    const chat = (await created.json()) as ChatSummary;
    expect(chat.id).toBe(100);

    const sent = await post(`/api/chats/${chat.id}/messages`, {
      text: "How are we doing?",
      mode: "thinking",
    });
    expect(sent.status).toBe(201);
    await expect(sent.json()).resolves.toEqual({
      user_message_id: 1000,
      assistant_message_id: 1001,
    });

    const detail = await fetch(`${APP}/api/chats/${chat.id}`);
    expect(detail.status).toBe(200);
    await expect(detail.json()).resolves.toMatchObject({
      id: 100,
      title: "How are we doing?",
    });
  });

  test("an empty question is refused and an unknown chat is gone", async () => {
    await signIn();
    const created = (await (await post("/api/chats", {})).json()) as ChatSummary;
    const empty = await post(`/api/chats/${created.id}/messages`, { text: "  " });
    expect(empty.status).toBe(400);
    await expect(empty.json()).resolves.toMatchObject({ error: "empty_text" });

    const missing = await fetch(`${APP}/api/chats/999`);
    expect(missing.status).toBe(404);
    await expect(missing.json()).resolves.toMatchObject({ error: "not_found" });
  });

  test("GET /api/status reports waiting questions and the data date", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/status`);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      questions_waiting: 3,
      data_through: "2025-10-26",
      spending: {
        state: "ok",
        spent_usd: 41.2,
        limit_usd: 150,
        warn_percent: 80,
        percent_used: 27.47,
      },
    });
  });

  test("POST /api/messages/:id/finish stops the running answer", async () => {
    await signIn();
    const finished = await post("/api/messages/4/finish", {});
    expect(finished.status).toBe(200);
    const detail = await fetch(`${APP}/api/chats/2`);
    await expect(detail.json()).resolves.toMatchObject({
      messages: [{ id: 3 }, { id: 4, status: "stopped" }],
    });
    const missing = await post("/api/messages/999/finish", {});
    expect(missing.status).toBe(404);
  });

  test("PATCH /api/chats/:id renames, rejects blank titles and unknown chats", async () => {
    await signIn();
    const renamed = await fetch(`${APP}/api/chats/1`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "  Fresh title  " }),
    });
    expect(renamed.status).toBe(200);
    await expect(renamed.json()).resolves.toMatchObject({ id: 1, title: "Fresh title" });
    const list = (await (await fetch(`${APP}/api/chats`)).json()) as ChatSummary[];
    expect(list.find((chat) => chat.id === 1)?.title).toBe("Fresh title");
    const blank = await fetch(`${APP}/api/chats/1`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "   " }),
    });
    expect(blank.status).toBe(400);
    await expect(blank.json()).resolves.toMatchObject({ error: "empty_title" });
    const missing = await fetch(`${APP}/api/chats/999`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Gone" }),
    });
    expect(missing.status).toBe(404);
  });

  test("DELETE /api/chats/:id refuses a running answer, then deletes", async () => {
    await signIn();
    const created = (await (await post("/api/chats", {})).json()) as ChatSummary;
    await post(`/api/chats/${created.id}/messages`, { text: "Still thinking?", mode: "thinking" });
    const refused = await fetch(`${APP}/api/chats/${created.id}`, { method: "DELETE" });
    expect(refused.status).toBe(409);
    await expect(refused.json()).resolves.toMatchObject({ error: "chat_running" });
    const gone = await fetch(`${APP}/api/chats/${created.id}`);
    expect(gone.status).toBe(200);
    await post("/api/messages/1001/finish", {});
    const deleted = await fetch(`${APP}/api/chats/${created.id}`, { method: "DELETE" });
    expect(deleted.status).toBe(200);
    const list = (await (await fetch(`${APP}/api/chats`)).json()) as ChatSummary[];
    expect(list.some((chat) => chat.id === created.id)).toBe(false);
    const detail = await fetch(`${APP}/api/chats/${created.id}`);
    expect(detail.status).toBe(404);
    const missing = await fetch(`${APP}/api/chats/999`, { method: "DELETE" });
    expect(missing.status).toBe(404);
  });

  test("GET /api/status reports the overridden waiting count", async () => {
    await signIn();
    localStorage.setItem("charie-mock-waiting-override", "1");
    expect(waitingOverride()).toBe(1);
    const response = await fetch(`${APP}/api/status`);
    await expect(response.json()).resolves.toMatchObject({ questions_waiting: 1 });
  });

  test("GET /api/usage returns the populated demo month and zeros", async () => {
    await signIn();
    const demo = await (await fetch(`${APP}/api/usage?month=2025-10`)).json();
    expect(demo).toMatchObject({
      month: "2025-10",
      spent_usd: 41.2,
      limit_usd: 150,
      state: "ok",
    });
    expect(demo.per_day).toHaveLength(27);
    expect(demo.top_questions[0]).toMatchObject({ chat_id: 3 });
    const empty = await (await fetch(`${APP}/api/usage?month=2025-01`)).json();
    expect(empty).toMatchObject({ month: "2025-01", spent_usd: 0, state: "ok" });
    expect(empty.per_group).toEqual([]);
    const bad = await fetch(`${APP}/api/usage?month=soon`);
    expect(bad.status).toBe(400);
    await expect(bad.json()).resolves.toMatchObject({ error: "bad_month" });
  });

  test("GET /api/knowledge lists, filters and 404s unknown keys", async () => {
    await signIn();
    const all = await (await fetch(`${APP}/api/knowledge`)).json();
    expect(all.entries.length).toBeGreaterThan(10);
    expect(all).toMatchObject({ version: 14, status: "published" });
    const words = await (await fetch(`${APP}/api/knowledge?kind=word`)).json();
    expect(words.entries.length).toBeGreaterThan(0);
    expect(words.entries.every((e: { kind: string }) => e.kind === "word")).toBe(true);
    const found = await (await fetch(`${APP}/api/knowledge?q=lunch`)).json();
    expect(found.entries.map((e: { key: string }) => e.key)).toContain("default.lunch");
    const stable = await (await fetch(`${APP}/api/knowledge/metric.net_sales`)).json();
    expect(stable).toMatchObject({ key: "metric.net_sales", name: "Net sales" });
    const missing = await fetch(`${APP}/api/knowledge/nope`);
    expect(missing.status).toBe(404);
    const suggested = await post("/api/knowledge/metric.net_sales/suggest", { text: "  Try this  " });
    expect(suggested.status).toBe(200);
    expect(mockSuggestions()).toHaveLength(1);
    const empty = await post("/api/knowledge/metric.net_sales/suggest", { text: "   " });
    expect(empty.status).toBe(400);
  });

  test("PATCH /api/settings validates the budget and clears paused", async () => {
    await signIn();
    const bad = await fetch(`${APP}/api/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spend_limit_usd: -5, spend_warn_percent: 150 }),
    });
    expect(bad.status).toBe(400);
    await expect(bad.json()).resolves.toMatchObject({ error: "bad_limit" });
    const ok = await fetch(`${APP}/api/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spend_limit_usd: 300, spend_warn_percent: 70 }),
    });
    expect(ok.status).toBe(200);
    await expect(ok.json()).resolves.toMatchObject({ spend_limit_usd: 300, spend_warn_percent: 70 });
  });

  test("POST /api/chats needs a session", async () => {
    const response = await post("/api/chats", {});
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toMatchObject({ error: "not_logged_in" });
  });
});
