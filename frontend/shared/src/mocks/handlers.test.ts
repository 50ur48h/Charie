import { afterAll, afterEach, beforeAll, describe, expect, test } from "vitest";
import { setupServer } from "msw/node";
import { SESSION_KEY, handlers } from "./handlers";
import type { ChatSummary } from "../api/types";

const server = setupServer(...handlers);

const APP = "https://charie.invalid";

beforeAll(() => {
  server.listen();
});

afterEach(() => {
  server.resetHandlers();
  localStorage.clear();
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
});
