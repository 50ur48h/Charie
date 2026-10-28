import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "./client";
import { applyFeedEvent, emptyFeed, type FeedState } from "./message-feed";
import { loggedOutMe } from "./hooks";

// Server-sent events over fetch (architecture 09, "The live stream").
// Each event carries a running-number id; the client passes the last one
// it saw back as Last-Event-ID so the server re-sends what was missed.

export interface StreamEvent {
  id: string | null;
  event: string;
  data: string;
}

export const MAX_STREAM_RETRIES = 5;

/** Bounded backoff between reconnects: 0.5s, 1s, 2s, 4s, then 8s. */
export function backoffDelayMs(attempt: number): number {
  return Math.min(8000, 500 * 2 ** Math.max(0, attempt));
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort(): void {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

async function throwForStatus(response: Response): Promise<void> {
  if (response.ok) return;
  let message: string | undefined;
  try {
    message = ((await response.json()) as { message?: unknown }).message as string;
  } catch {
    message = undefined;
  }
  throw new ApiError(
    response.status,
    `http_${response.status}`,
    message ?? (response.status === 401 ? "Please sign in again." : "Can't reach Charie. Check your connection and try again."),
  );
}

/** Open the event stream. Rejects with ApiError on HTTP errors. */
export async function fetchStream(
  url: string,
  options?: { lastEventId?: string | null; signal?: AbortSignal },
): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(url, {
      headers: {
        Accept: "text/event-stream",
        ...(options?.lastEventId ? { "Last-Event-ID": options.lastEventId } : {}),
      },
      signal: options?.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(0, "network", "Can't reach Charie. Check your connection and try again.");
  }
  await throwForStatus(response);
  return response;
}

/**
 * Parse SSE framing from a response body: events end at blank lines,
 * `data:` lines join with newlines, `:comments` and unknown fields are
 * skipped. Resolves when the stream ends; an abort resolves quietly.
 */
export async function readStreamEvents(
  response: Response,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = "";
  let id: string | null = null;
  let name = "message";
  let data: string[] | null = null;

  function dispatch(): void {
    if (data === null) {
      id = null;
      name = "message";
      return;
    }
    onEvent({ id, event: name, data: data.join("\n") });
    id = null;
    name = "message";
    data = null;
  }

  function feed(chunk: string): void {
    buffer += chunk;
    let at;
    while ((at = buffer.indexOf("\n")) !== -1) {
      const raw = buffer.slice(0, at);
      buffer = buffer.slice(at + 1);
      const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
      if (line === "") {
        dispatch();
      } else if (line.startsWith(":")) {
        // Comment (heartbeat): skip.
      } else {
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "id") id = value;
        else if (field === "event") name = value;
        else if (field === "data") (data ??= []).push(value);
        // Unknown fields are skipped.
      }
    }
  }

  try {
    for (;;) {
      if (signal?.aborted) {
        await reader.cancel().catch(() => undefined);
        return;
      }
      const { done, value } = await reader.read();
      if (done) break;
      feed(decoder.decode(value, { stream: true }));
    }
    feed(decoder.decode());
    if (buffer !== "") feed("\n");
  } catch (error) {
    // A dropped connection reads as a failure; an abort is quiet.
    if (error instanceof DOMException && error.name === "AbortError") return;
    if (signal?.aborted) return;
    throw error instanceof ApiError
      ? error
      : new ApiError(0, "network", "Can't reach Charie. Check your connection and try again.");
  } finally {
    reader.releaseLock();
  }
}

function isAbort(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof ApiError && error.code === "AbortError")
  );
}

/**
 * Follow one assistant message's stream while it runs. Reconnects with
 * Last-Event-ID on drops (bounded backoff); a terminal done stops
 * retries and refetches the saved answer. Aborting (navigation, logout,
 * finish) closes quietly. A 401 returns to login.
 */
export function useAnswerStream(
  chatId: number,
  messageId: number | null,
  onDone: () => Promise<void> | void,
): FeedState {
  const client = useQueryClient();
  const [feed, setFeed] = useState<FeedState>(() => emptyFeed());
  const doneRef = useRef(false);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    setFeed(emptyFeed());
    doneRef.current = false;
    if (messageId === null) return;
    const controller = new AbortController();
    let stopped = false;
    let lastEventId: string | null = null;
    let attempts = 0;

    async function follow(): Promise<void> {
      while (!stopped && !doneRef.current) {
        try {
          const response = await fetchStream(`/api/messages/${messageId}/stream`, {
            lastEventId,
            signal: controller.signal,
          });
          await readStreamEvents(
            response,
            (event) => {
              if (stopped) return;
              if (event.id !== null) lastEventId = event.id;
              if (event.event === "done") doneRef.current = true;
              setFeed((prev) => applyFeedEvent(prev, { ...event, data: parseData(event.data) }));
            },
            controller.signal,
          );
          if (stopped || doneRef.current) break;
          attempts += 1;
          if (attempts > MAX_STREAM_RETRIES) {
            setFeed((prev) =>
              prev.done === null
                ? {
                    ...prev,
                    error: {
                      code: "network",
                      message: "Can't reach Charie. Check your connection and try again.",
                    },
                  }
                : prev,
            );
            break;
          }
          await sleep(backoffDelayMs(attempts - 1), controller.signal);
        } catch (error) {
          if (stopped || isAbort(error) || controller.signal.aborted) break;
          if (error instanceof ApiError && error.status === 401) {
            client.setQueryData(["me"], loggedOutMe());
            break;
          }
          if (doneRef.current) break;
          attempts += 1;
          if (attempts > MAX_STREAM_RETRIES) {
            setFeed((prev) =>
              prev.done === null
                ? {
                    ...prev,
                    error: {
                      code: error instanceof ApiError ? error.code : "network",
                      message:
                        error instanceof ApiError
                          ? error.message
                          : "Can't reach Charie. Check your connection and try again.",
                    },
                  }
                : prev,
            );
            break;
          }
          try {
            await sleep(backoffDelayMs(attempts - 1), controller.signal);
          } catch {
            break;
          }
        }
      }
      // A sidebar switch or unmount during these awaits must not let this
      // completion touch the new chat: re-check the stop flag each time.
      if (doneRef.current && !stopped) {
        await client.invalidateQueries({ queryKey: ["chat", chatId] });
        if (stopped) return;
        await onDoneRef.current();
      }
    }

    void follow();
    return () => {
      stopped = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatId, messageId]);

  return feed;
}

function parseData(data: string): unknown {
  try {
    return JSON.parse(data) as unknown;
  } catch {
    console.warn("Ignoring stream event (bad JSON):", data.slice(0, 80));
    return null;
  }
}
