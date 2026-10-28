import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { Toaster } from "@charie/shared";
import { ChatPage } from "./ChatPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const FRESH = {
  id: 3,
  title: "Fresh chat",
  created_at: "2026-10-28T08:00:00.000Z",
  updated_at: "2026-10-28T08:00:00.000Z",
  messages: [],
  thinking: [],
  thinking_summary: null,
};

const RUNNING = {
  ...FRESH,
  messages: [
    { id: 10, role: "user", text: "Slow question?", status: "done", mode: "thinking" },
    { id: 11, role: "assistant", text: "", status: "thinking", mode: "thinking" },
  ],
};

function stubFetch() {
  const posts: string[] = [];
  let posted = false;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/status")) {
        return Promise.resolve(json({ questions_waiting: 0, data_through: "2025-10-26" }));
      }
      if (url.includes("/messages") && method === "POST") {
        posts.push(url);
        posted = true;
        return Promise.resolve(json({ user_message_id: 10, assistant_message_id: 11 }, 201));
      }
      if (url.includes("/api/chats/3")) return Promise.resolve(json(posted ? RUNNING : FRESH));
      return Promise.resolve(json({}));
    }),
  );
  return posts;
}

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  const router = createMemoryRouter(
    [
      {
        path: "/chat/:chatId",
        element: (
          <>
            <Toaster />
            <ChatPage />
          </>
        ),
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("ChatPage", () => {
  test("a same-tick double submit sends once", async () => {
    const posts = stubFetch();
    renderAt("/chat/3");
    await screen.findByRole("textbox", { name: "Ask a question" });
    fireEvent.change(screen.getByRole("textbox", { name: "Ask a question" }), {
      target: { value: "Slow question?" },
    });
    // Both dispatches run before React can re-render: without the in-flight
    // guard the second one reads the stale unlocked state and posts again.
    const form = document.querySelector("form")!;
    // Raw dispatches, not fireEvent: nothing flushes React between them, so
    // both see the same pre-click render — exactly the stale-state double
    // submit the in-flight guard exists for.
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    expect(await screen.findByText("Thinking…")).toBeTruthy();
    expect(posts).toHaveLength(1);
  });

  test("an unknown chat says it is gone", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve(
          url.includes("/api/chats/999")
            ? json({ error: "not_found", message: "That chat is gone." }, 404)
            : json({ questions_waiting: 0, data_through: null }),
        ),
      ),
    );
    renderAt("/chat/999");
    expect(await screen.findByRole("heading", { name: "That chat is gone." })).toBeTruthy();
  });
});
