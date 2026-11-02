import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { Toaster } from "@charie/shared";
import { NewChatPage } from "./NewChatPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const SUMMARIES = [
  { id: 1, title: "How are we doing this month?", created_at: "2026-10-28T08:00:00.000Z", updated_at: "2026-10-28T08:00:00.000Z" },
  { id: 2, title: "Top dishes by profit", created_at: "2026-10-28T07:00:00.000Z", updated_at: "2026-10-28T07:00:00.000Z" },
  { id: 3, title: "Why did delivery drop in Austin?", created_at: "2026-10-27T08:00:00.000Z", updated_at: "2026-10-27T08:00:00.000Z" },
];

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(mode: "ok" | "send-fails") {
  const posts: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url.includes("/api/status")) {
        return Promise.resolve(json({
            questions_waiting: 3,
            knowledge: { version: 2, entries: 248, documents: 1, published_at: "2026-11-20T10:00:00Z" },
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
      if (url.includes("/messages")) {
        posts.push(url);
        if (mode === "send-fails") {
          return Promise.resolve(
            json({ error: "busy", message: "Charie is having trouble. Please try again." }, 500),
          );
        }
        return Promise.resolve(json({ user_message_id: 1000, assistant_message_id: 1001 }, 201));
      }
      if (url.includes("/api/chats") && method === "POST") {
        posts.push(url);
        return Promise.resolve(
          json(
            { id: 100, title: "New chat", created_at: "2026-10-28T09:00:00.000Z", updated_at: "2026-10-28T09:00:00.000Z" },
            201,
          ),
        );
      }
      if (url.includes("/api/chats")) return Promise.resolve(json(SUMMARIES));
      return Promise.resolve(json({}));
    }),
  );
  return posts;
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: (
          <>
            <Toaster />
            <NewChatPage />
          </>
        ),
      },
      { path: "/chat/:chatId", element: <div>Thread page</div> },
    ],
    { initialEntries: ["/"] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function composer(): HTMLTextAreaElement {
  return screen.getByRole("textbox", { name: "Ask a question" }) as HTMLTextAreaElement;
}

describe("NewChatPage", () => {
  test("a sample question fills the composer", async () => {
    stubFetch("ok");
    renderPage();
    await screen.findByText("Pick up where you left off");
    fireEvent.click(screen.getByRole("button", { name: /How are we doing this month\?/ }));
    expect(composer().value).toBe("How are we doing this month?");
  });

  test("an empty question keeps Ask disabled without calling the API", async () => {
    const posts = stubFetch("ok");
    renderPage();
    await screen.findByText("Pick up where you left off");
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(composer(), { target: { value: "   " } });
    expect((screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled).toBe(true);
    expect(posts).toEqual([]);
  });

  test("a double submit creates one chat and opens it", async () => {
    const posts = stubFetch("ok");
    renderPage();
    await screen.findByText("Pick up where you left off");
    fireEvent.change(composer(), { target: { value: "How are we doing?" } });
    const ask = screen.getByRole("button", { name: "Ask" });
    fireEvent.click(ask);
    fireEvent.click(ask);
    expect(await screen.findByText("Thread page")).toBeTruthy();
    expect(posts.filter((url) => !url.includes("/messages"))).toHaveLength(1);
    expect(posts.filter((url) => url.includes("/messages"))).toHaveLength(1);
  });

  test("a failed send keeps the text and says what happened", async () => {
    stubFetch("send-fails");
    renderPage();
    await screen.findByText("Pick up where you left off");
    fireEvent.change(composer(), { target: { value: "How are we doing?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(
      await screen.findByText("Charie is having trouble. Please try again."),
    ).toBeTruthy();
    expect(composer().value).toBe("How are we doing?");
  });
});
