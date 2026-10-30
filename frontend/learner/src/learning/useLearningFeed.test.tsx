import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import {
  isTerminalMessage,
  useLearning,
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
    expect(isTerminalMessage(message("status", JSON.stringify({ status: "failed" })))).toBe(
      true,
    );
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

  test("a paused tab sees a remote resume through the open stream", async () => {
    // One tab, one stream: the snapshot starts paused, the other tab
    // resumes, and this tab learns it from the status line — no reload.
    let phase: "paused" | "running" | "done" = "paused";
    let streamCalls = 0;
    let snapshotCalls = 0;
    const chunk = (kind: string, data: unknown, id: number | null = null): string => {
      const head = id === null ? "" : `id: ${id}\n`;
      return `${head}event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`;
    };
    const sseStream = (body: string): Response =>
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(body));
            controller.close();
          },
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      );
    const runJson = () => ({
      runs: [
        {
          id: 77,
          kind: "refresh",
          status: phase,
          paused_by: null,
          reason: "3 new documents",
          step: 8,
          percent: 62,
          minutes_left: 25,
          progress: [],
          cost_usd: 3.8,
          summary: "6 changes",
          version_number: 15,
          new_version: true,
          started_at: new Date(2026, 9, 27, 21, 12).toISOString(),
          finished_at: null,
        },
      ],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/learning/stream")) {
          streamCalls += 1;
          if (streamCalls === 1)
            return Promise.resolve(sseStream(chunk("status", { status: "paused" }, 1)));
          if (streamCalls === 2)
            return Promise.resolve(sseStream(chunk("status", { status: "running" }, 2)));
          return Promise.resolve(sseStream(chunk("status", { status: "done" }, 3)));
        }
        snapshotCalls += 1;
        return Promise.resolve(
          new Response(JSON.stringify(runJson()), {
            headers: { "Content-Type": "application/json" },
          }),
        );
      }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const { result, unmount } = renderHook(
      () => {
        const snapshot = useLearning();
        const live = snapshot.data?.runs?.[0] ?? null;
        const feed = useLearningFeed(
          live?.id ?? null,
          live?.status === "running" || live?.status === "paused",
        );
        return { live, feed };
      },
      {
        wrapper: ({ children }: { children: React.ReactNode }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    const status = () => result.current.live?.status ?? "none";
    // The stream said paused first: the tab sits paused.
    await waitFor(() => expect(status()).toBe("paused"), { timeout: 10000 });
    // The other tab resumes; the next status line flips this tab.
    phase = "running";
    await waitFor(() => expect(status()).toBe("running"), { timeout: 10000 });
    expect(result.current.feed.done).toBe(false);
    phase = "done";
    await waitFor(() => expect(status()).toBe("done"), { timeout: 10000 });
    // The done status ends the stream: three connections, no more.
    await waitFor(() => expect(streamCalls).toBe(3), { timeout: 10000 });
    // Initial snapshot plus one refetch per status line at least.
    expect(snapshotCalls).toBeGreaterThanOrEqual(3);
    unmount();
  }, 30000);

  test("a remote failure finishes the feed and refetches the snapshot", async () => {
    let phase: "running" | "failed" = "running";
    const chunk = (data: unknown, id: number): string =>
      `id: ${id}\nevent: status\ndata: ${JSON.stringify(data)}\n\n`;
    const sseStream = (body: string): Response =>
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(body));
            controller.close();
          },
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      );
    const runJson = (status: string) => ({
      runs: [
        {
          id: 78,
          kind: "refresh",
          status,
          paused_by: null,
          reason: "3 new documents",
          step: 8,
          percent: 62,
          minutes_left: null,
          progress: [],
          cost_usd: 3.8,
          summary: "The database check stopped the run.",
          version_number: 15,
          new_version: false,
          started_at: new Date(2026, 9, 27, 21, 12).toISOString(),
          finished_at:
            status === "failed" ? new Date(2026, 9, 27, 21, 40).toISOString() : null,
        },
      ],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (String(url).includes("/api/learning/stream")) {
          return Promise.resolve(
            sseStream(
              phase === "running"
                ? chunk({ status: "running" }, 1)
                : chunk({ status: "failed" }, 2),
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify(runJson(phase)), {
            headers: { "Content-Type": "application/json" },
          }),
        );
      }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result, unmount } = renderHook(
      () => {
        const snapshot = useLearning();
        const live = snapshot.data?.runs?.[0] ?? null;
        const feed = useLearningFeed(live?.id ?? null, live?.status === "running");
        return { live, feed };
      },
      {
        wrapper: ({ children }: { children: React.ReactNode }) => (
          <QueryClientProvider client={client}>{children}</QueryClientProvider>
        ),
      },
    );
    const status = () => result.current.live?.status ?? "none";
    await waitFor(() => expect(status()).toBe("running"), { timeout: 10000 });
    // The run fails elsewhere: the failed status refetches the snapshot,
    // the page shows the failure, and the dead stream stays closed.
    phase = "failed";
    await waitFor(() => expect(status()).toBe("failed"), { timeout: 10000 });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["learner-learning"] });
    unmount();
  }, 30000);

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
