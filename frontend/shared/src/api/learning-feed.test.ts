import { describe, expect, test } from "vitest";
import { applyLearningEvent, emptyLearningFeed } from "./learning-feed";

const line = (seq: number) => ({
  event: "found",
  id: String(seq),
  data: JSON.stringify({
    seq,
    at: "2026-10-27T21:31:00+05:30",
    step: 8,
    kind: "found",
    message: "Net sales matches the finance report: Q3 = $3.91M.",
  }),
});

describe("learning-feed", () => {
  test("adds a line once", () => {
    const once = applyLearningEvent(emptyLearningFeed(), line(6));
    expect(once.lines).toHaveLength(1);
    expect(once.lines[0]).toMatchObject({ seq: 6, step: 8, kind: "found" });
    const twice = applyLearningEvent(once, line(6));
    expect(twice.lines).toHaveLength(1);
    expect(twice).toBe(once);
  });

  test("progress updates the step and percent", () => {
    const next = applyLearningEvent(emptyLearningFeed(), {
      event: "progress",
      id: "7",
      data: JSON.stringify({ step: 8, done: 33, total: 45, percent: 64 }),
    });
    expect(next.step).toBe(8);
    expect(next.percent).toBe(64);
    expect(next.lines).toHaveLength(0);
  });

  test("status done finishes the run", () => {
    const next = applyLearningEvent(emptyLearningFeed(), {
      event: "status",
      id: "99",
      data: JSON.stringify({ status: "done" }),
    });
    expect(next.done).toBe(true);
  });

  test("new_run_resets_feed", () => {
    const oldRun = applyLearningEvent(emptyLearningFeed(), line(6));
    expect(oldRun.lines).toHaveLength(1);
    // A new run starts from a fresh feed: old lines are gone and the new
    // run's first line applies cleanly.
    const fresh = emptyLearningFeed();
    expect(fresh.lines).toHaveLength(0);
    expect(fresh.lastSeq).toBe(0);
    expect(fresh.done).toBe(false);
    const restarted = applyLearningEvent(fresh, line(1));
    expect(restarted.lines).toHaveLength(1);
    expect(restarted.lines[0]).toMatchObject({ seq: 1 });
  });

  test("reconnect_snapshot", () => {
    // Cut mid-run after line 6; the reconnect replays it, then the snapshot
    // carries newer progress and a new line.
    const before = applyLearningEvent(emptyLearningFeed(), line(6));
    const replayed = applyLearningEvent(before, line(6));
    expect(replayed).toBe(before);
    const progressed = applyLearningEvent(replayed, {
      event: "progress",
      id: "7",
      data: JSON.stringify({ step: 8, done: 40, total: 45, percent: 70 }),
    });
    expect(progressed.step).toBe(8);
    expect(progressed.percent).toBe(70);
    expect(progressed.lines).toHaveLength(1);
    const next = applyLearningEvent(progressed, line(7));
    expect(next.lines.map((entry) => entry.seq)).toEqual([6, 7]);
  });
});
