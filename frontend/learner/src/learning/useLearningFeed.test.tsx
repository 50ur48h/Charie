import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import {
  isTerminalMessage,
  useLearningFeed,
  type IncomingMessage,
} from "@charie/shared";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function sse(lines: string[]): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(lines.join("")));
        controller.close();
      },
    }),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}

function line(seq: number, kind: string, message: string): string {
  const data = JSON.stringify({
    seq,
    at: "2026-10-27T21:31:00+05:30",
    step: 8,
    kind,
    message,
  });
  return `id: ${seq}\nevent: ${kind}\ndata: ${data}\n\n`;
}

function renderFeed(runId = 4) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(client, "invalidateQueries");
  const rendered = renderHook(({ id }: { id: number }) => useLearningFeed(id, true), {
    initialProps: { id: runId },
    wrapper: ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
  return { ...rendered, invalidate };
}


describe("isTerminalMessage", () => {
  test("only a done line or a done status finishes the run", () => {
    const message = (event: string, data: string): IncomingMessage => ({ event, data, id: null });
    expect(isTerminalMessage(message("done", "{}"))).toBe(true);
    expect(isTerminalMessage(message("status", JSON.stringify({ status: "done" })))).toBe(true);
    expect(isTerminalMessage(message("status", JSON.stringify({ status: "running" })))).toBe(
      false,
    );
    expect(isTerminalMessage(message("status", "not json"))).toBe(false);
    expect(isTerminalMessage(message("found", "{}"))).toBe(false);
    expect(isTerminalMessage(message("progress", "{}"))).toBe(false);
  });
});

describe("useLearningFeed reconnect", () => {
  test("a cut connection reconnects and finishes without duplicates", async () => {
    const seenIds: (string | null)[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
        const lastId = new Headers(init?.headers).get("Last-Event-ID");
        seenIds.push(lastId);
        if (lastId === null) {
          // Cut mid-run: one line, then the connection ends with no done.
          return Promise.resolve(sse([line(1, "found", "First line.")]));
        }
        // Reconnect replays the missed line, then the run finishes.
        return Promise.resolve(
          sse([
            line(1, "found", "First line."),
            line(2, "found", "Second line."),
            line(3, "done", "Learning finished."),
          ]),
        );
      }),
    );
    const { result, invalidate, unmount } = renderFeed();

    await waitFor(() => expect(result.current.lines).toHaveLength(3), { timeout: 10000 });
    expect(result.current.lines.map((entry) => entry.seq)).toEqual([1, 2, 3]);
    expect(result.current.done).toBe(true);
    // Reconnected once, resuming where it left off.
    expect(seenIds).toEqual([null, "1"]);
    await waitFor(
      () => expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learner-learning"] }),
      { timeout: 5000 },
    );
    unmount();
  });

  test("a cut connection refetches the snapshot, then finishes once", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(sse([line(1, "found", "First line.")]))),
    );
    const { result, invalidate, unmount } = renderFeed();
    // The cut ends the first stream with no terminal message: the hook
    // refetches the snapshot (progress the feed missed) and reconnects.
    await waitFor(
      () =>
        expect(
          invalidate.mock.calls.filter(
            (call) =>
              JSON.stringify(call[0]) === '{"queryKey":["learner-learning"]}',
          ),
        ).toHaveLength(1),
      { timeout: 10000 },
    );
    expect(result.current.done).toBe(false);
    expect(result.current.lines.map((entry) => entry.seq)).toEqual([1]);
    unmount();
  });

  test("the stream carries the run id and resumes with Last-Event-ID", async () => {
    const seen: Array<{ url: string; lastId: string | null }> = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        seen.push({
          url,
          lastId: new Headers(init?.headers).get("Last-Event-ID"),
        });
        return Promise.resolve(
          sse([
            line(1, "found", "First line."),
            line(2, "found", "Second line."),
            line(3, "done", "Learning finished."),
          ]),
        );
      }),
    );
    const { result, unmount } = renderFeed(4);
    await waitFor(() => expect(result.current.done).toBe(true), {
      timeout: 10000,
    });
    expect(seen.length).toBeGreaterThan(0);
    for (const call of seen) {
      expect(call.url).toContain("run_id=4");
    }
    unmount();
  });

  test("a new run resets the feed instead of mixing lines", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("run_id=5")) {
          return Promise.resolve(sse([line(1, "found", "New run line.")]));
        }
        return Promise.resolve(
          sse([
            line(1, "found", "Old run line one."),
            line(2, "found", "Old run line two."),
          ]),
        );
      }),
    );
    const { result, rerender, unmount } = renderFeed(4);
    await waitFor(() => expect(result.current.lines).toHaveLength(2), {
      timeout: 10000,
    });
    rerender({ id: 5 });
    await waitFor(
      () =>
        expect(result.current.lines.map((entry) => entry.message)).toEqual([
          "New run line.",
        ]),
      { timeout: 10000 },
    );
    unmount();
  });
});
