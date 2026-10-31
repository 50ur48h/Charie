import type { LearningEvent, LearningEventKind, LearningRun } from "../../api/learner-types";
import { learner, saveLearner, saveSetup, setup } from "./state";

// Mock-only clocks (P04.5 documents, P04.7 runs). The ticks are pure store
// updates so Vitest calls them directly; startLearnerMockTimers wires the
// intervals in the browser, never in Vitest, and never for ?mock=still.

// Design feed lines, in order (learner-learning.html). ok lines grow step 6,
// ask lines grow step 10.
const LINES: { kind: LearningEventKind; message: string }[] = [
  { kind: "found", message: "Net sales matches the finance report: Q3 = $3.91M." },
  { kind: "info", message: "orders.total includes tax and the delivery fee. Noted." },
  {
    kind: "found",
    message: "Average order = net sales ÷ number of orders. Never an average of averages.",
  },
  { kind: "question", message: "Coupon codes look like NAME + MMYY. Added a question for you." },
  { kind: "found", message: "Delivery share: the parts add up to the total." },
  {
    kind: "info",
    message: "Labor cost: two possible formulas give different numbers. Trying both on the data…",
  },
  { kind: "found", message: "Food cost % sits inside the Ops handbook target (28–31%)." },
  {
    kind: "question",
    message:
      "The refund policy says refunds come out of sales, but the data shows them separately. Added a question.",
  },
  { kind: "found", message: "Promotions calendar matches the coupon codes for September and October." },
  { kind: "info", message: "New menu guide: 6 new dishes found. Adding them to the dictionary." },
];

const STEP8_NAMES = ["average order", "food cost %", "delivery share", "labor cost %", "refunds"];

// Top percent each step owns: step 8 runs from 55 to 74.
const STEP_TOPS = [4, 11, 19, 24, 34, 44, 54, 74, 79, 84, 94, 100];

function stepForPercent(percent: number): number {
  return STEP_TOPS.findIndex((top) => percent <= top) + 1;
}

// Live feed lines per run (mock only, never persisted). The design run opens
// with its first 5 lines at 9:26–9:30 pm; the timer appends from line 6.
const eventLog = new Map<number, LearningEvent[]>();
const lastLineAt = new Map<number, number>();
const lineIndex = new Map<number, number>();

function seedDesignHistory(run: LearningRun): void {
  // Only the design-world run (never a run the user started, which carries
  // the current time): it opens mid-run with 5 lines already in the feed.
  if (
    run.started_at !== "2026-10-27T21:12:00+05:30" ||
    run.reason !== "3 new documents" ||
    eventLog.has(run.id)
  ) {
    return;
  }
  const base = Date.parse("2026-10-27T21:26:00+05:30");
  eventLog.set(
    run.id,
    LINES.slice(0, 5).map((line, i) => ({
      seq: i + 1,
      at: new Date(base + i * 60000).toISOString(),
      step: run.step,
      kind: line.kind,
      message: line.message,
    })),
  );
  lastLineAt.set(run.id, base + 4 * 60000);
  lineIndex.set(run.id, 5);
}

// The newest run by start time (what the screens call runs[0]).
export function newestRun(): LearningRun | undefined {
  let best: LearningRun | undefined;
  for (const run of learner().runs) {
    if (!best || Date.parse(run.started_at) >= Date.parse(best.started_at)) best = run;
  }
  return best;
}

// Tests only: clear the feed lines so each test starts from the seed.
export function resetTimerState(): void {
  eventLog.clear();
  lastLineAt.clear();
  lineIndex.clear();
  listeners.clear();
}

export function getRunEvents(runId: number): LearningEvent[] {
  const run = learner().runs.find((r) => r.id === runId);
  if (run) seedDesignHistory(run);
  return [...(eventLog.get(runId) ?? [])];
}

type RunListener = (event: LearningEvent) => void;

const listeners = new Map<number, Set<RunListener>>();

export function subscribeRunEvents(runId: number, listener: RunListener): () => void {
  let set = listeners.get(runId);
  if (!set) {
    set = new Set();
    listeners.set(runId, set);
  }
  set.add(listener);
  return () => {
    set.delete(listener);
  };
}

function emit(runId: number, event: LearningEvent): void {
  listeners.get(runId)?.forEach((listener) => listener(event));
}

function addLine(run: LearningRun, at: Date): void {
  const log = eventLog.get(run.id) ?? [];
  const index = lineIndex.get(run.id) ?? 0;
  const line = LINES[index % LINES.length];
  const event: LearningEvent = {
    seq: log.length + 1,
    at: at.toISOString(),
    step: run.step,
    kind: line.kind,
    message: line.message,
  };
  log.push(event);
  eventLog.set(run.id, log);
  lineIndex.set(run.id, index + 1);
  lastLineAt.set(run.id, at.getTime());
  if (line.kind === "found") {
    const step6 = run.progress.find((s) => s.step === 6);
    if (step6) step6.done += 1;
  }
  if (line.kind === "question") {
    const step10 = run.progress.find((s) => s.step === 10);
    if (step10) step10.done += 1;
  }
  emit(run.id, event);
}

// P04.5: the fake reader. Reading documents gain 25 (at 100 they are read:
// +7 facts, 4 pages if the count was unknown). While a run is going, new
// documents start reading; otherwise they wait for Refresh knowledge base.
// A retry reads even with no run (it is a job of its own).
export function readDocumentsTick(now: Date = new Date()): void {
  const store = learner();
  let changed = false;
  for (const doc of store.documents) {
    if (doc.status !== "reading" || doc.progress === null) continue;
    const progress = Math.min(100, doc.progress + 25);
    doc.progress = progress;
    changed = true;
    if (progress >= 100) {
      doc.status = "learned";
      doc.progress = null;
      doc.learned_at = now.toISOString();
      doc.fact_count += 7;
      if (doc.pages === null) doc.pages = 4;
    }
  }
  const running = store.runs.some((run) => run.status === "running");
  if (running) {
    for (const doc of store.documents) {
      if (doc.status === "new") {
        doc.status = "reading";
        doc.progress = 0;
        changed = true;
      }
    }
  }
  if (changed) saveLearner();
}

// First runs learn the business, so finishing one fills the step-5 report.
const DESIGN_READINESS = {
  numbers_checked: 41,
  numbers_total: 45,
  numbers_waiting: 4,
  practice_right: 183,
  practice_total: 200,
  weak_area: "Food waste",
  weak_area_why: "Few documents about it",
} as const;

// P04.7: one run tick every 2.2 s while a run is going. +2 percent (the step
// is the band the percent falls in), a feed line at most once a minute, and
// a finished run at 100 with its draft ready to check.
export function advanceRunTick(now: Date = new Date()): void {
  const store = learner();
  const run = store.runs.find((r) => r.status === "running");
  if (!run) return;
  if (run.progress.length !== 12) {
    run.progress = Array.from({ length: 12 }, (_, i) => ({
      step: i + 1,
      done: 0,
      total: null,
      note: "Waiting",
    }));
  }
  run.percent = Math.min(100, run.percent + 2);
  run.step = stepForPercent(run.percent);
  for (const step of run.progress) {
    if (step.step < run.step && step.note === "Waiting") step.note = "Done";
  }
  const current = run.progress[run.step - 1];
  if (run.step === 8) {
    current.total = 45;
    const name = STEP8_NAMES[current.done % STEP8_NAMES.length];
    current.done += 1;
    current.note = `Testing "${name}" · ${current.done} of 45`;
  } else {
    current.done += 1;
    current.note = "Working on it";
  }
  run.minutes_left = Math.ceil((100 - run.percent) * 0.66);
  run.cost_usd = Math.round((run.cost_usd + 0.05) * 100) / 100;
  seedDesignHistory(run);
  // A fresh run says its first line right away; after that, at most one
  // line a minute. The design run opens with its history already seeded.
  const last = lastLineAt.get(run.id);
  if (last === undefined || now.getTime() - last >= 60000) addLine(run, now);
  if (run.percent >= 100) {
    run.status = "done";
    run.minutes_left = null;
    run.finished_at = now.toISOString();
    if (run.kind === "refresh") {
      // The refresh consumed its snapshot: removals and the notes save
      // it learned. Failed runs skip this, so their changes stay pending.
      const finished = learner();
      finished.refresh_consumed = {
        removed: finished.documents
          .filter((doc) => doc.status === "removed")
          .map((doc) => doc.id),
        notes_at: setup().notes.saved_at,
      };
    }
    const done: LearningEvent = {
      seq: (eventLog.get(run.id) ?? []).length + 1,
      at: now.toISOString(),
      step: 12,
      kind: "done",
      message: `Learning finished. Draft version ${run.version_number} is ready for you to check.`,
    };
    eventLog.get(run.id)?.push(done);
    emit(run.id, done);
    if (run.kind === "first") {
      const slice = setup();
      slice.readiness = { ...DESIGN_READINESS };
      saveSetup();
    }
  }
  saveLearner();
}

// Browser only: the reader every second, runs every 2.2 s, as in the design.
// Never called in Vitest (tests call the ticks) or for ?mock=still.
export function startLearnerMockTimers(): () => void {
  const documents = setInterval(() => readDocumentsTick(), 1000);
  const runs = setInterval(() => advanceRunTick(), 2200);
  return () => {
    clearInterval(documents);
    clearInterval(runs);
  };
}
