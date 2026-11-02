// "Ask Charie about this" on the Questions page (P12.2).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { createMemoryRouter, RouterProvider } from "react-router";
import { NewChatPage } from "./NewChatPage";
import { QuestionsPage } from "./QuestionsPage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const QUESTION = {
  id: 7,
  status: "waiting",
  rank: 1,
  importance: "high",
  topic: "Sales",
  title: "What counts as revenue?",
  body: "Pick one.",
  evidence: { summary: "Two definitions in use." },
  options: [
    { id: "a", label: "Net sales" },
    { id: "b", label: "Gross sales" },
  ],
  defaultOption: "a",
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch() {
  const posts: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (method !== "GET") posts.push(url);
      if (url.includes("/api/questions")) {
        if (url.includes("waiting")) return Promise.resolve(json({ questions: [QUESTION] }));
        return Promise.resolve(json({ questions: [] }));
      }
      if (url.includes("/api/status")) {
        return Promise.resolve(
          json({
            questions_waiting: 1,
            knowledge: { version: 2, entries: 10, documents: 1, published_at: "2026-11-20T10:00:00Z" },
            data: null,
            learning: null,
            spending: null,
            learner_url: null,
          }),
        );
      }
      if (url.includes("/api/chats")) return Promise.resolve(json({ chats: [] }));
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
      { path: "/questions", element: <QuestionsPage /> },
      { path: "/", element: <NewChatPage /> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

describe("QuestionsPage", () => {
  test("Ask Charie about this fills the question box", async () => {
    const posts = stubFetch();
    const router = renderAt("/questions");
    await screen.findByText("What counts as revenue?");
    fireEvent.click(screen.getByRole("button", { name: "Ask Charie about this" }));
    const box = (await screen.findByRole("textbox", { name: "Ask a question" })) as HTMLTextAreaElement;
    await waitFor(() => {
      expect(box.value).toBe("Help me decide: What counts as revenue?");
    });
    expect(router.state.location.pathname).toBe("/");
    expect(posts).toEqual([]);
  });

  test("the waiting tab explains an empty list", async () => {
    stubFetch();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) => {
        if (url.includes("/api/questions")) return Promise.resolve(json({ questions: [] }));
        if (url.includes("/api/status")) return Promise.resolve(json({ questions_waiting: 0 }));
        return Promise.resolve(json({}));
      }),
    );
    renderAt("/questions");
    await screen.findByText("Nothing waiting. Charie will ask here when it finds something only you can answer.");
  });
});
