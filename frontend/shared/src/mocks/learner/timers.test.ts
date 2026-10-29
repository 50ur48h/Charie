import { describe, expect, test } from "vitest";
import { learner, resetLearnerMock } from "./state";
import { advanceRunTick, getRunEvents, readDocumentsTick, resetTimerState } from "./timers";

function designStore() {
  resetLearnerMock("design");
  resetTimerState();
  return learner();
}

describe("timers", () => {
  test("a reading document becomes learned", () => {
    const store = designStore();
    const guide = store.documents.find((doc) => doc.file_name === "Menu guide, autumn.pdf");
    expect(guide?.status).toBe("reading");
    const facts = guide?.fact_count ?? 0;
    const at = new Date("2026-10-27T21:40:00+05:30");
    readDocumentsTick(at);
    expect(guide?.status).toBe("reading");
    expect(guide?.progress).toBe(89);
    readDocumentsTick(at);
    expect(guide?.status).toBe("learned");
    expect(guide?.progress).toBeNull();
    expect(guide?.pages).toBe(12);
    expect(guide?.fact_count).toBe(facts + 7);
    expect(guide?.learned_at).toBe(at.toISOString());
  });

  test("new documents wait when no run is going", () => {
    const store = designStore();
    for (const run of store.runs) run.status = "done";
    const fresh = store.documents.filter((doc) => doc.status === "new");
    expect(fresh.length).toBeGreaterThan(0);
    readDocumentsTick(new Date("2026-10-27T21:40:00+05:30"));
    expect(store.documents.filter((doc) => doc.status === "new").length).toBe(fresh.length);
  });

  test("new documents start reading while a run is going", () => {
    const store = designStore();
    readDocumentsTick(new Date("2026-10-27T21:40:00+05:30"));
    const fresh = store.documents.filter((doc) => doc.status === "new");
    expect(fresh.length).toBe(0);
    expect(
      store.documents.filter((doc) => doc.status === "reading" && doc.progress === 0).length,
    ).toBeGreaterThan(0);
  });

  test("a run tick adds a line and 2 percent", () => {
    const store = designStore();
    const run = store.runs.find((r) => r.id === 4);
    expect(run?.percent).toBe(62);
    expect(getRunEvents(4)).toHaveLength(5);
    advanceRunTick(new Date("2026-10-27T21:35:00+05:30"));
    expect(run?.percent).toBe(64);
    expect(run?.step).toBe(8);
    expect(run?.minutes_left).toBe(Math.ceil((100 - 64) * 0.66));
    const events = getRunEvents(4);
    expect(events).toHaveLength(6);
    expect(events[5]).toMatchObject({ seq: 6, step: 8, kind: "info" });
    expect(run?.cost_usd).toBeGreaterThan(3.8);
  });

  test("a run reaches done at 100", () => {
    const store = designStore();
    const run = store.runs.find((r) => r.id === 4);
    if (!run) throw new Error("design run 4 is missing");
    run.percent = 98;
    const at = new Date("2026-10-27T23:00:00+05:30");
    advanceRunTick(at);
    expect(run.percent).toBe(100);
    expect(run.status).toBe("done");
    expect(run.finished_at).toBe(at.toISOString());
    const events = getRunEvents(4);
    expect(events[events.length - 1]).toMatchObject({
      kind: "done",
      message: `Learning finished. Draft version ${run.version_number} is ready for you to check.`,
    });
  });
});
