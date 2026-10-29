import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Toaster, type LearnerTodo } from "@charie/shared";
import { TodoList } from "./TodoList";

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

function renderList(items: LearnerTodo[]) {
  const posted: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/api/todos/") && (init?.method ?? "GET") === "POST") {
        posted.push(url);
        const id = Number(url.split("/").at(-2));
        const found = items.find((item) => item.id === id);
        if (found) {
          found.status = "dismissed";
          found.done_at = new Date().toISOString();
          found.result = "Dismissed by you";
        }
        return Promise.resolve(json({ todo: found }));
      }
      if (url.includes("/api/todos")) {
        return Promise.resolve(json({ todos: items.filter((item) => item.status === "open") }));
      }
      return Promise.resolve(json({}));
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <Toaster />
      <TodoList />
    </QueryClientProvider>,
  );
  return { posted };
}

const HOUR = 3600 * 1000;

function todo(id: number, chatTitle: string | null): LearnerTodo {
  return {
    id,
    kind: id === 1 ? "correction" : "unknown_word",
    text: id === 1 ? "Net sales should leave out refunds." : 'What is a "MEGA deal"?',
    details: {
      chat_title: chatTitle,
      words: id === 1 ? "Net sales should leave out refunds." : 'What is a "MEGA deal"?',
    },
    status: "open",
    result: null,
    created_at: new Date(Date.now() - HOUR).toISOString(),
    done_at: null,
  };
}

describe("TodoList", () => {
  test("shows the 2 open items", async () => {
    renderList([todo(1, "How are we doing this month?"), todo(2, null)]);
    await waitFor(() => {
      expect(screen.getByText("To check")).not.toBeNull();
    });
    expect(screen.getByText("Net sales should leave out refunds.")).not.toBeNull();
    expect(screen.getByText('What is a "MEGA deal"?')).not.toBeNull();
    expect(screen.getByText("Correction")).not.toBeNull();
    expect(screen.getByText("Unknown word")).not.toBeNull();
    expect(screen.getByText(/From “How are we doing this month\?” · 1 hour ago/)).not.toBeNull();
    expect(screen.getByText(/From you · 1 hour ago/)).not.toBeNull();
  });

  test("dismiss removes an item", async () => {
    const user = userEvent.setup();
    const { posted } = renderList([todo(1, "How are we doing this month?"), todo(2, null)]);
    await waitFor(() => {
      expect(screen.getByText('What is a "MEGA deal"?')).not.toBeNull();
    });
    const dismissals = screen.getAllByRole("button", { name: "Dismiss" });
    await user.click(dismissals[0]);
    await waitFor(() => {
      expect(posted).toContain("/api/todos/1/dismiss");
    });
    await waitFor(() => {
      expect(screen.queryByText("Net sales should leave out refunds.")).toBeNull();
    });
    expect(screen.getByText('What is a "MEGA deal"?')).not.toBeNull();
    expect(screen.getByText("Dismissed. Charie won't look at it.")).not.toBeNull();
  });

  test("hides with no open items", async () => {
    renderList([]);
    await waitFor(() => {
      expect(screen.queryByText("To check")).toBeNull();
    });
  });
});
