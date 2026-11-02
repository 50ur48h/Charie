import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "vitest";
import { setupServer } from "msw/node";
import { SESSION_KEY, handlers } from "./handlers";
import type { ChatSummary } from "../api/types";
import { resetMockChats } from "./sampleChat";
import { resetMockQuestions, waitingOverride } from "./sampleQuestions";
import { resetMockKnowledge, mockSuggestions } from "./sampleKnowledge";
import { resetMockUsage } from "./sampleUsage";
import { learner, resetLearnerMock } from "./learner/state";
import { publishedBase } from "./learner/versions";

const server = setupServer(...handlers);

const APP = "https://charie.invalid";

beforeAll(() => {
  server.listen();
});

afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
  resetLearnerMock("design");
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
  test("GET /api/chats gives the 9 sample chats, newest first", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/chats`);
    expect(response.status).toBe(200);
    const chats = (await response.json()) as ChatSummary[];
    expect(chats).toHaveLength(9);
    expect(chats.map((chat) => chat.title)).toEqual([
      "December delivery review",
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
    expect(empty.status).toBe(422);
    await expect(empty.json()).resolves.toMatchObject({ error: "empty_question" });

    const long = await post(`/api/chats/${created.id}/messages`, { text: "x".repeat(2001) });
    expect(long.status).toBe(422);
    await expect(long.json()).resolves.toMatchObject({ error: "question_too_long" });

    const quick = await post(`/api/chats/${created.id}/messages`, {
      text: "Net sales?",
      mode: "quick",
    });
    expect(quick.status).toBe(422);
    await expect(quick.json()).resolves.toMatchObject({ error: "quick_not_ready" });

    const missing = await fetch(`${APP}/api/chats/999`);
    expect(missing.status).toBe(404);
    await expect(missing.json()).resolves.toMatchObject({ error: "not_found" });
  });

  test("a second question while running is refused", async () => {
    await signIn();
    const created = (await (await post("/api/chats", {})).json()) as ChatSummary;
    await post(`/api/chats/${created.id}/messages`, { text: "First?" });
    const second = await post(`/api/chats/${created.id}/messages`, { text: "Second?" });
    expect(second.status).toBe(409);
    await expect(second.json()).resolves.toMatchObject({ error: "question_running" });
  });

  test("GET /api/status reports waiting questions and the data date", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/status`);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      questions_waiting: 3,
      knowledge: {
        version: 14,
        entries: publishedBase().length,
        documents: learner().documents.filter((doc) => doc.status !== "removed").length,
        published_at: "2026-10-20T02:06:00+05:30",
      },
      data: {
        name: "Bella Forno database",
        kind: "postgres",
        status: "connected",
        data_through: "2025-10-26",
      },
      learning: { status: "done", step_title: "Self-test", percent: 100 },
      spending: {
        state: "ok",
        spent_usd: 41.2,
        limit_usd: 150,
        warn_percent: 80,
        percent_used: 27.47,
      },
      learner_url: "http://localhost:5174",
    });
  });

  test("the still-learning fake state reports no knowledge and refuses asking", async () => {
    await signIn();
    localStorage.setItem("charie-mock-still-learning", "1");
    const status = await (await fetch(`${APP}/api/status`)).json();
    expect(status.knowledge).toEqual({ version: null, entries: 0, documents: 0, published_at: null });
    expect(status.learning).toEqual({ status: "running", step_title: "Read your documents", percent: 38 });
    const created = (await (await post("/api/chats", {})).json()) as ChatSummary;
    const refused = await post(`/api/chats/${created.id}/messages`, { text: "How are we doing?" });
    expect(refused.status).toBe(409);
    await expect(refused.json()).resolves.toMatchObject({ error: "still_learning" });
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
    const alreadyDone = await post("/api/messages/2/finish", {});
    expect(alreadyDone.status).toBe(409);
    await expect(alreadyDone.json()).resolves.toMatchObject({ error: "not_running" });
  });

  test("PATCH /api/chats/:id renames, rejects bad titles and unknown chats", async () => {
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
    expect(blank.status).toBe(422);
    await expect(blank.json()).resolves.toMatchObject({ error: "bad_title" });
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
    await expect(refused.json()).resolves.toMatchObject({ error: "question_running" });
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
      model: "muse-wonder-1.0",
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
    expect(all.version).toMatchObject({ number: 14, status: "published" });
    expect(all.counts).toMatchObject({ metric: 4, default: 3 });
    expect(all.needs_review).toBe(4);
    const words = await (await fetch(`${APP}/api/knowledge?kind=default`)).json();
    expect(words.entries.length).toBeGreaterThan(0);
    expect(words.entries.every((e: { kind: string }) => e.kind === "default")).toBe(true);
    const found = await (await fetch(`${APP}/api/knowledge?q=lunch`)).json();
    expect(found.entries.map((e: { key: string }) => e.key)).toContain("default.lunch");
    const stable = await (await fetch(`${APP}/api/knowledge/metric.net_sales`)).json();
    expect(stable.entry).toMatchObject({ key: "metric.net_sales", title: "Net sales" });
    expect(stable.version).toMatchObject({ number: 14, status: "published" });
    expect(Array.isArray(stable.history)).toBe(true);
    const missing = await fetch(`${APP}/api/knowledge/nope`);
    expect(missing.status).toBe(404);
    await expect(missing.json()).resolves.toMatchObject({
      error: "not_found",
      message: "There's no knowledge entry called nope.",
    });
    const suggested = await post("/api/knowledge/metric.net_sales/suggest", { text: "  Try this  " });
    expect(suggested.status).toBe(201);
    await expect(suggested.json()).resolves.toMatchObject({ todo_id: 1 });
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
    await expect(bad.json()).resolves.toMatchObject({ error: "bad_setting" });
    const ok = await fetch(`${APP}/api/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spend_limit_usd: 300, spend_warn_percent: 70 }),
    });
    expect(ok.status).toBe(200);
    await expect(ok.json()).resolves.toMatchObject({ spend_limit_usd: 300, spend_warn_percent: 70 });
  });

  test("GET /api/settings returns the full defaults", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/settings`);
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({
      theme: "sage",
      answer_length: "normal",
      number_format: "short",
      thinking_minutes: 10,
      show_reading: true,
      memory_on: true,
      spend_limit_usd: 150,
      spend_warn_percent: 80,
      time_zone: null,
      self_test_question_count: 50,
    });
    const body = (await (await fetch(`${APP}/api/settings`)).json()) as Record<string, unknown>;
    expect("password_hash" in body).toBe(false);
  });

  test("PATCH /api/settings refuses each bad value with the exact message", async () => {
    await signIn();
    const cases: [Record<string, unknown>, string][] = [
      [{ theme: "banana" }, "Theme must be one of: sage, lavender, mist, seafoam, mauve, slate."],
      [{ answer_length: "brief" }, "Answer length must be short, normal or detailed."],
      [{ number_format: "long" }, "Number format must be short or full."],
      [{ thinking_minutes: 16 }, "Thinking time must be a whole number of minutes from 2 to 15."],
      [{ thinking_minutes: 2.5 }, "Thinking time must be a whole number of minutes from 2 to 15."],
      [{ self_test_question_count: 0 }, "Practice questions must be a whole number from 1 to 200."],
      [{ self_test_question_count: 201 }, "Practice questions must be a whole number from 1 to 200."],
      [{ show_reading: "yes" }, "`show_reading` must be true or false."],
      [{ memory_on: 1 }, "`memory_on` must be true or false."],
      [{ spend_limit_usd: 0 }, "The monthly limit must be between $0.01 and $100,000."],
      [{ spend_limit_usd: 200000 }, "The monthly limit must be between $0.01 and $100,000."],
      [{ spend_warn_percent: 0 }, "The warning level must be a whole number from 1 to 99."],
      [{ spend_warn_percent: 100 }, "The warning level must be a whole number from 1 to 99."],
      [{ time_zone: "Mars/Olympus" }, "Unknown time zone: `Mars/Olympus`. Use a name like Asia/Kolkata."],
      [{ setup_done: true }, "This setting can't be changed here: `setup_done`."],
      [{ password_hash: "x" }, "This setting can't be changed here: `password_hash`."],
      [{ nope: 1 }, "Unknown setting: `nope`."],
    ];
    for (const [patch, message] of cases) {
      const response = await fetch(`${APP}/api/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      expect(response.status).toBe(400);
      await expect(response.json()).resolves.toMatchObject({ error: "bad_setting", message });
    }
  });

  test("PATCH /api/settings saves all or nothing", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_length: "detailed", thinking_minutes: 99 }),
    });
    expect(response.status).toBe(400);
    const saved = (await (await fetch(`${APP}/api/settings`)).json()) as {
      answer_length: string;
    };
    expect(saved.answer_length).toBe("normal");
    const ok = await fetch(`${APP}/api/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer_length: "detailed", thinking_minutes: 12, time_zone: "Asia/Kolkata" }),
    });
    expect(ok.status).toBe(200);
    await expect(ok.json()).resolves.toMatchObject({
      answer_length: "detailed",
      thinking_minutes: 12,
      time_zone: "Asia/Kolkata",
    });
  });

  test("POST /api/password changes the mock password", async () => {
    await signIn();
    const wrong = await post("/api/password", { current: "nope", new: "new-password-1" });
    expect(wrong.status).toBe(400);
    await expect(wrong.json()).resolves.toMatchObject({ error: "wrong_password" });
    const short = await post("/api/password", { current: "bella-forno", new: "short" });
    expect(short.status).toBe(400);
    await expect(short.json()).resolves.toMatchObject({ error: "password_too_short" });
    const changed = await post("/api/password", { current: "bella-forno", new: "new-password-1" });
    expect(changed.status).toBe(200);
    const oldLogin = await post("/api/login", { password: "bella-forno" });
    expect(oldLogin.status).toBe(401);
    const newLogin = await post("/api/login", { password: "new-password-1" });
    expect(newLogin.status).toBe(200);
  });

  test("memories list, delete one, and forget everything", async () => {
    await signIn();
    const listed = await fetch(`${APP}/api/memories`);
    expect(listed.status).toBe(200);
    const memories = (await listed.json()) as { id: number }[];
    expect(memories).toHaveLength(3);
    const missing = await fetch(`${APP}/api/memories/999`, { method: "DELETE" });
    expect(missing.status).toBe(404);
    const deleted = await fetch(`${APP}/api/memories/${memories[0].id}`, { method: "DELETE" });
    expect(deleted.status).toBe(200);
    const after = (await (await fetch(`${APP}/api/memories`)).json()) as unknown[];
    expect(after).toHaveLength(2);
    const cleared = await fetch(`${APP}/api/memories`, { method: "DELETE" });
    expect(cleared.status).toBe(200);
    const empty = (await (await fetch(`${APP}/api/memories`)).json()) as unknown[];
    expect(empty).toHaveLength(0);
  });

  test("GET /api/me names the app addresses", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/me`);
    await expect(response.json()).resolves.toMatchObject({
      chat_url: "http://localhost:5173",
      learner_url: "http://localhost:5174",
    });
  });

  test("GET /api/documents returns the 14 design documents, newest first", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/documents`);
    expect(response.status).toBe(200);
    const { documents } = (await response.json()) as {
      documents: { file_name: string; status: string; uploaded_at: string }[];
    };
    expect(documents).toHaveLength(14);
    expect(documents[0]).toMatchObject({
      file_name: "Promotions calendar 2026.xlsx",
      status: "new",
    });
    const times = documents.map((doc) => Date.parse(doc.uploaded_at));
    expect([...times].sort((a, b) => b - a)).toEqual(times);
    expect(documents.some((doc) => doc.status === "removed")).toBe(false);
  });

  test("GET /api/learning returns the 4 runs, newest first", async () => {
    await signIn();
    const response = await fetch(`${APP}/api/learning`);
    expect(response.status).toBe(200);
    const { runs } = (await response.json()) as {
      runs: { id: number; kind: string; status: string }[];
    };
    expect(runs.map((run) => run.id)).toEqual([4, 3, 2, 1]);
    expect(runs[0]).toMatchObject({ kind: "refresh", status: "running" });
  });

  test("learner addresses need a session", async () => {
    for (const path of ["/api/documents", "/api/learning"]) {
      const response = await fetch(`${APP}${path}`);
      expect(response.status).toBe(401);
      await expect(response.json()).resolves.toMatchObject({ error: "not_logged_in" });
    }
  });

  test("POST /api/chats needs a session", async () => {
    const response = await post("/api/chats", {});
    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toMatchObject({ error: "not_logged_in" });
  });
});
