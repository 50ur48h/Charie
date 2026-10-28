import { describe, expect, test } from "vitest";
import {
  backoffDelayMs,
  fetchStream,
  MAX_STREAM_RETRIES,
  readStreamEvents,
  type StreamEvent,
} from "./stream";

function streamResponse(chunks: (string | Uint8Array)[]): Response {
  const encoded = chunks.map((chunk) =>
    typeof chunk === "string" ? new TextEncoder().encode(chunk) : chunk,
  );
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const part of encoded) controller.enqueue(part);
      controller.close();
    },
  });
  return new Response(stream);
}

async function collect(response: Response): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  await readStreamEvents(response, (event) => {
    events.push(event);
  });
  return events;
}

describe("stream client", () => {
  test("chunk_boundaries reassembles split frames and multibyte text", () => {
    const euro = new TextEncoder().encode("id: 1\nevent: text\ndata: 2€\n\n");
    // Split inside the € (3 bytes) and inside the event framing.
    const parts = [euro.slice(0, 24), euro.slice(24, 26), euro.slice(26)];
    return expect(collect(streamResponse(parts))).resolves.toEqual([
      { id: "1", event: "text", data: "2€" },
    ]);
  });

  test("multiline_data joins with newlines and comments are skipped", () => {
    return expect(
      collect(
        streamResponse([
          ": heartbeat\n",
          "id: 2\nevent: note\ndata: line one\ndata: line two\n\n",
          "id: 3\ndata: bare\n\n",
        ]),
      ),
    ).resolves.toEqual([
      { id: "2", event: "note", data: "line one\nline two" },
      { id: "3", event: "message", data: "bare" },
    ]);
  });

  test("last_event_id sends the header", async () => {
    const seen: Record<string, string> = {};
    const realFetch = globalThis.fetch;
    globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      headers.forEach((value, key) => {
        seen[key] = value;
      });
      return new Response("id: 1\ndata: {}\n\n", {
        headers: { "Content-Type": "text/event-stream" },
      });
    }) as typeof fetch;
    try {
      await fetchStream("/api/messages/8/stream", { lastEventId: "41" });
      expect(seen["last-event-id"]).toBe("41");
      expect(seen["accept"]).toBe("text/event-stream");
    } finally {
      globalThis.fetch = realFetch;
    }
  });

  test("abort resolves quietly with what arrived", async () => {
    const events: StreamEvent[] = [];
    const controller = new AbortController();
    const pending = readStreamEvents(
      new Response(
        new ReadableStream({
          start(c) {
            c.enqueue(new TextEncoder().encode("id: 1\ndata: {\"a\":1}\n\n"));
          },
        }),
      ),
      (event) => {
        events.push(event);
        controller.abort();
      },
      controller.signal,
    );
    await expect(pending).resolves.toBeUndefined();
    expect(events).toEqual([{ id: "1", event: "message", data: '{"a":1}' }]);
  });

  test("backoff is bounded", () => {
    expect([0, 1, 2, 3, 4, 5, 9].map(backoffDelayMs)).toEqual([
      500, 1000, 2000, 4000, 8000, 8000, 8000,
    ]);
    expect(MAX_STREAM_RETRIES).toBe(5);
  });
});
