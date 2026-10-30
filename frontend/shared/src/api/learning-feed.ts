import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { LearningEvent } from "./learner-types";
import {
  MAX_STREAM_RETRIES,
  backoffDelayMs,
  fetchStream,
  isAbort,
  readStreamEvents,
  sleep,
} from "./stream";

// Live feed for the Learning page (architecture 09, "The live stream").
// The stream sends `event` (a feed line), `progress` and `status` messages;
// events carry a running-number seq and the client skips ones it saw.

export interface LearningFeedState {
  lines: LearningEvent[];
  lastSeq: number;
  percent: number | null;
  step: number | null;
  done: boolean;
}

export function emptyLearningFeed(): LearningFeedState {
  return { lines: [], lastSeq: 0, percent: null, step: null, done: false };
}

export interface IncomingMessage {
  event: string;
  data: string;
  id: string | null;
}

/** A message that means the run finished: a done line or a done status. */
export function isTerminalMessage(message: IncomingMessage): boolean {
  if (message.event === "done") return true;
  if (message.event !== "status") return false;
  try {
    return (JSON.parse(message.data) as { status?: unknown }).status === "done";
  } catch {
    return false;
  }
}

function parseData(data: string): Record<string, unknown> | null {
  try {
    return JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** Fold one stream message into the feed. Pure, so tests pin it. */
export function applyLearningEvent(
  state: LearningFeedState,
  message: IncomingMessage,
): LearningFeedState {
  const data = parseData(message.data);
  if (!data) return state;
  if (message.event === "progress") {
    const percent = typeof data.percent === "number" ? data.percent : null;
    const step = typeof data.step === "number" ? data.step : null;
    return percent === null && step === null ? state : { ...state, percent, step };
  }
  if (message.event === "status") {
    return data.status === "done" ? { ...state, done: true } : state;
  }
  const seq = typeof data.seq === "number" ? data.seq : null;
  const kind = data.kind;
  if (
    seq === null ||
    seq <= state.lastSeq ||
    (kind !== "info" &&
      kind !== "found" &&
      kind !== "question" &&
      kind !== "warning" &&
      kind !== "done")
  ) {
    return state;
  }
  const line: LearningEvent = {
    seq,
    at: typeof data.at === "string" ? data.at : "",
    step: typeof data.step === "number" ? data.step : 0,
    kind,
    message: typeof data.message === "string" ? data.message : "",
  };
  return {
    ...state,
    lines: [...state.lines, line].slice(-50),
    lastSeq: seq,
    done: state.done || kind === "done",
  };
}

/**
 * Follow a run's feed while it is going. Opens GET /api/learning/stream
 * with the last seen seq and refetches the run list when a terminal
 * message says the run finished. A connection that ends first is cut,
 * not done: reconnect with the last seq (bounded backoff, no duplicates).
 * Quiet when there is no run or the page goes away.
 */
export function useLearningFeed(runId: number | null, active: boolean): LearningFeedState {
  const client = useQueryClient();
  const [feed, setFeed] = useState<LearningFeedState>(() => emptyLearningFeed());
  const doneRef = useRef(false);

  useEffect(() => {
    setFeed(emptyLearningFeed());
    doneRef.current = false;
    if (runId === null || !active) return;
    const controller = new AbortController();
    let stopped = false;
    let lastEventId: string | null = null;
    let attempts = 0;

    async function follow(): Promise<void> {
      while (!stopped && !doneRef.current) {
        try {
          // run_id plus Last-Event-ID: the server replays this run only,
          // so a new run never mixes its lines into the old feed.
          const response = await fetchStream(
            `/api/learning/stream?run_id=${runId}`,
            {
              lastEventId,
              signal: controller.signal,
            },
          );
          await readStreamEvents(
            response,
            (event) => {
              if (stopped) return;
              if (event.id !== null) lastEventId = event.id;
              if (isTerminalMessage(event)) doneRef.current = true;
              setFeed((prev) => applyLearningEvent(prev, event));
            },
            controller.signal,
          );
          if (stopped || doneRef.current) break;
          // The connection ended mid-run: refetch the snapshot so the
          // page shows missed progress, then reconnect where we left off.
          await client.invalidateQueries({ queryKey: ["learner-learning"] });
          attempts += 1;
          if (attempts > MAX_STREAM_RETRIES) break;
          await sleep(backoffDelayMs(attempts - 1), controller.signal);
        } catch (error) {
          if (stopped || isAbort(error) || controller.signal.aborted) break;
          if (doneRef.current) break;
          attempts += 1;
          if (attempts > MAX_STREAM_RETRIES) break;
          try {
            await sleep(backoffDelayMs(attempts - 1), controller.signal);
          } catch {
            break;
          }
        }
      }
      // A sidebar switch or unmount during these awaits must not let this
      // completion touch the new run: re-check the stop flag each time.
      if (doneRef.current && !stopped) {
        await client.invalidateQueries({ queryKey: ["learner-learning"] });
      }
    }

    void follow();
    return () => {
      stopped = true;
      controller.abort();
    };
  }, [client, runId, active]);

  // A done line means the run just finished: refresh the runs so the page
  // shows the summary (the 5 s poll stops once the run is done).
  const finished = feed.done;
  useEffect(() => {
    if (finished) void client.invalidateQueries({ queryKey: ["learner-learning"] });
  }, [client, finished]);

  return feed;
}
