import { afterAll, afterEach, beforeAll, describe, expect, test } from "vitest";
import { setupServer } from "msw/node";
import { handlers } from "./handlers";
import type { ChatSummary } from "../api/types";

const server = setupServer(...handlers);

beforeAll(() => {
  server.listen();
});

afterEach(() => {
  server.resetHandlers();
});

afterAll(() => {
  server.close();
});

describe("mock handlers", () => {
  test("GET /api/chats gives the 8 sample chats, newest first", async () => {
    const response = await fetch("https://charie.invalid/api/chats");
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
    const response = await fetch("https://charie.invalid/api/me");
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toMatchObject({ logged_in: true });
  });

  test("GET /api/health says ok", async () => {
    const response = await fetch("https://charie.invalid/api/health");
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true });
  });

  test("an address without a fake answer gets 501 and a plain-English message", async () => {
    const response = await fetch("https://charie.invalid/api/nothing-yet", {
      method: "POST",
      body: "{}",
    });
    expect(response.status).toBe(501);
    await expect(response.json()).resolves.toMatchObject({
      error: "not_mocked",
      message: "The sample data doesn't cover this yet.",
    });
  });
});
