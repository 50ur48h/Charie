import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { LearningEvent } from "./learner-types";
import { fetchStream, readStreamEvents } from "./stream";

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

interface IncomingMessage {
  event: string;
  data: string;
  id: string | null;
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
 * with the last seen seq and refetches the run list when it finishes.
 * Quiet when there is no run or the page goes away.
 */
export function useLearningFeed(runId: number | null, active: boolean): LearningFeedState {
  const client = useQueryClient();
  const [feed, setFeed] = useState<LearningFeedState>(() => emptyLearningFeed());

  useEffect(() => {
    setFeed(emptyLearningFeed());
    if (runId === null || !active) return;
    const controller = new AbortController();
    let stopped = false;

    async function follow(): Promise<void> {
      let lastEventId: string | null = null;
      let failures = 0;
      for (;;) {
        if (stopped) return;
        try {
          const response = await fetchStream("/api/learning/stream", {
            lastEventId,
            signal: controller.signal,
          });
          await readStreamEvents(
            response,
            (event) => {
              if (stopped) return;
              if (event.id !== null) lastEventId = event.id;
              setFeed((prev) => applyLearningEvent(prev, event));
            },
            controller.signal,
          );
          if (stopped) return;
          // The stream only ends when the run is done: refresh the runs.
          await client.invalidateQueries({ queryKey: ["learner-learning"] });
          return;
        } catch {
          if (stopped || controller.signal.aborted) return;
          failures += 1;
          if (failures > 3) return;
          await new Promise((resolve) => setTimeout(resolve, failures * 1000));
        }
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
