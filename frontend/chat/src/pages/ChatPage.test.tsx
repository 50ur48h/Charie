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

const NOW = "2026-10-28T08:00:00.000Z";

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
    { id: 10, role: "user", text: "Slow question?", status: "done", started_at: "2026-10-28T08:00:00.000Z" },
    { id: 11, role: "assistant", status: "thinking", mode: "thinking", answer: null, thinking: [], summary: null },
  ],
};

function stubFetch(startRunning = false) {
  const posts: string[] = [];
  const streams: string[] = [];
  let posted = false;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/status")) {
        return Promise.resolve(json({
            questions_waiting: 0,
            knowledge: { version: null, entries: 0, documents: 0, published_at: null },
            data: {
              name: "Bella Forno database",
              kind: "postgres",
              status: "connected",
              data_through: "2025-10-26",
            },
            learning: null,
            spending: {
              state: "ok",
              spent_usd: 1,
              limit_usd: 150,
              warn_percent: 80,
              percent_used: 1,
            },
          }));
      }
      if (url.includes("/messages") && method === "POST") {
        posts.push(url);
        posted = true;
        return Promise.resolve(json({ user_message_id: 10, assistant_message_id: 11 }, 201));
      }
      if (url.includes("/stream")) {
        streams.push(url);
        return Promise.resolve(
          new Response('id: 1' + "\n" + 'event: done' + "\n" + 'data: {"message_id":11,"status":"done"}' + "\n" + "\n", {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          }),
        );
      }
      if (url.includes("/api/chats/3"))
        return Promise.resolve(json(startRunning || posted ? RUNNING : FRESH));
      return Promise.resolve(json({}));
    }),
  );
  return { posts, streams };
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
  return { client };
}

describe("ChatPage", () => {
  test("a same-tick double submit sends once", async () => {
    const { posts } = stubFetch();
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

  test("a loaded running answer resumes its stream exactly once", async () => {
    const { streams } = stubFetch(true);
    renderAt("/chat/3");
    // The stub chat is already running: no send needed, the stream opens.
    expect(await screen.findByText("Thinking…")).toBeTruthy();
    const messageStreams = () => streams.filter((url) => url.includes("/api/messages/11/stream"));
    await vi.waitFor(() => {
      expect(messageStreams()).toHaveLength(1);
    });
    // Let any accidental reconnect loop fire: the count must hold, so a
    // frozen running state can never spin the stream open again.
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(messageStreams()).toHaveLength(1);
  });

  test("a done answer refetches the chat list for a new title", async () => {
    stubFetch(true);
    const { client } = renderAt("/chat/3");
    const refetch = vi.spyOn(client, "refetchQueries");
    await vi.waitFor(() => {
      expect(refetch).toHaveBeenCalledWith({ queryKey: ["chats"] });
    });
  });

  test("Try again downloads the real thing", async () => {
    const blobs: Blob[] = [];
    const realCreate = URL.createObjectURL;
    const realRevoke = URL.revokeObjectURL;
    URL.createObjectURL = ((blob: Blob) => {
      blobs.push(blob);
      return "blob:real";
    }) as typeof URL.createObjectURL;
    URL.revokeObjectURL = (() => undefined) as typeof URL.revokeObjectURL;
    try {
      const table = {
        type: "table",
        title: "Real table",
        columns: [
          { key: "city", label: "City" },
          { key: "sales", label: "Sales" },
        ],
        rows: [{ city: "Realville", sales: 42 }],
      };
      const assistant = (id: number, text: string, extra = {}) => ({
        id,
        role: "assistant",
        text,
        mode: "thinking" as const,
        status: "done" as const,
        thinking: [],
        summary: null,
        asked_at: NOW,
        answered_at: NOW,
        seconds: 3,
        steps: 4,
        answer: {
          message_id: id,
          kb_version: 14,
          data_through: "2025-10-26",
          blocks: [table],
        },
        feedback: null,
        ...extra,
      });
      let calls = 0;
      vi.stubGlobal(
        "fetch",
        vi.fn().mockImplementation((url: string) => {
          if (!url.includes("/api/chats/3")) {
            return Promise.resolve(new Response("not found", { status: 404 }));
          }
          calls += 1;
          if (calls <= 2) {
            return Promise.resolve(new Response("boom", { status: 500 }));
          }
          return Promise.resolve(
            json({
              id: 3,
              title: "Real chat",
              messages: [
                { id: 5, role: "user", text: "How are we doing?", asked_at: NOW },
                assistant(6, ""),
              ],
            }),
          );
        }),
      );
      renderAt("/chat/3");
      await screen.findByText("Couldn't load the chat.", undefined, { timeout: 5000 });
      fireEvent.click(screen.getByRole("button", { name: "Try again" }));
      await screen.findByRole("button", { name: "Download as CSV: Real table" }, { timeout: 5000 });
      fireEvent.click(screen.getByRole("button", { name: "Download as CSV: Real table" }));
      expect(blobs).toHaveLength(1);
      // This jsdom Blob has no .text(): read it with FileReader instead.
      const csv = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(reader.error);
        reader.readAsText(blobs[0]!);
      });
      expect(csv).toContain("Realville");
    } finally {
      URL.createObjectURL = realCreate;
      URL.revokeObjectURL = realRevoke;
    }
  });

  test("status is refreshed after an answer is done", async () => {
    stubFetch(true);
    const { client } = renderAt("/chat/3");
    const refetch = vi.spyOn(client, "refetchQueries");
    await vi.waitFor(() => {
      expect(refetch).toHaveBeenCalledWith({ queryKey: ["status"] });
    });
  });

  test("an unknown chat says it is gone", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve(
          url.includes("/api/chats/999")
            ? json({ error: "not_found", message: "That chat is gone." }, 404)
            : json({
            questions_waiting: 0,
            knowledge: { version: null, entries: 0, documents: 0, published_at: null },
            data: {
              name: "Bella Forno database",
              kind: "postgres",
              status: "connected",
              data_through: null,
            },
            learning: null,
            spending: {
              state: "ok",
              spent_usd: 1,
              limit_usd: 150,
              warn_percent: 80,
              percent_used: 1,
            },
          }),
        ),
      ),
    );
    renderAt("/chat/999");
    expect(await screen.findByRole("heading", { name: "That chat is gone." })).toBeTruthy();
  });
});
