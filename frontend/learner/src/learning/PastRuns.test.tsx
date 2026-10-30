import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import type { LearningRun, StepProgress } from "@charie/shared";
import { PastRuns } from "./PastRuns";

function steps(): StepProgress[] {
  return Array.from({ length: 12 }, (_, i) => ({ step: i + 1, done: 1, total: 1, note: "" }));
}

function run(overrides: Partial<LearningRun>): LearningRun {
  return {
    id: 1,
    kind: "nightly",
    status: "done",
    paused_by: null,
    reason: null,
    step: 12,
    percent: 100,
    minutes_left: null,
    progress: steps(),
    cost_usd: 1.2,
    summary: "No changes",
    version_number: 14,
    new_version: false,
    started_at: new Date(2026, 9, 26, 2, 0).toISOString(),
    finished_at: new Date(2026, 9, 26, 2, 4).toISOString(),
    ...overrides,
  };
}

describe("PastRuns", () => {
  test("shows the 4 design rows", () => {
    const runs = [
      run({
        id: 4,
        kind: "refresh",
        status: "running",
        reason: "3 new documents",
        step: 8,
        percent: 62,
        minutes_left: 25,
        summary: "6 changes",
        version_number: 15,
        new_version: true,
        started_at: new Date(2026, 9, 27, 21, 12).toISOString(),
        finished_at: null,
      }),
      run({ id: 3 }),
      run({
        id: 2,
        summary: "2 new coupon codes, 1 new restaurant",
        version_number: 14,
        new_version: true,
        started_at: new Date(2026, 9, 20, 2, 0).toISOString(),
        finished_at: new Date(2026, 9, 20, 2, 6).toISOString(),
      }),
      run({
        id: 1,
        kind: "first",
        summary: "236 entries, 12 questions for you",
        version_number: 1,
        new_version: true,
        started_at: new Date(2026, 8, 3, 10, 5).toISOString(),
        finished_at: new Date(2026, 8, 3, 11, 53).toISOString(),
      }),
    ];
    render(<PastRuns runs={runs} />);
    expect(screen.getByText("Refresh: 3 new documents")).toBeTruthy();
    expect(screen.getAllByText("Nightly check")).toHaveLength(2);
    expect(screen.getByText("First learning")).toBeTruthy();
    expect(screen.getByText("So far: 6 changes")).toBeTruthy();
    expect(screen.getByText("Draft version 15")).toBeTruthy();
    expect(screen.getByText("Version 14 kept")).toBeTruthy();
    expect(screen.getByText("Version 14")).toBeTruthy();
    expect(screen.getByText("Version 1")).toBeTruthy();
    expect(screen.getByText("4 min")).toBeTruthy();
  });
});
