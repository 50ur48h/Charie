import { afterEach, describe, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
import { MemoryRouter } from "react-router";
import type { LearningRun } from "@charie/shared";
import { RunHeader } from "./RunHeader";

function run(overrides: Partial<LearningRun>): LearningRun {
  return {
    id: 4,
    kind: "refresh",
    status: "running",
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
    ...overrides,
  };
}

function renderHeader(entry: LearningRun) {
  render(
    <MemoryRouter>
      <RunHeader run={entry} />
    </MemoryRouter>,
  );
}

describe("RunHeader", () => {
  test("running shows time left and cost", () => {
    renderHeader(run({}));
    expect(screen.getByText("62%")).toBeTruthy();
    expect(screen.getByText("Learning now")).toBeTruthy();
    expect(screen.getByText(/Started 9:12 pm/)).toBeTruthy();
    expect(screen.getByText(/about 25 minutes left/)).toBeTruthy();
    expect(screen.getByText(/\$3\.80 so far/)).toBeTruthy();
    expect(
      screen.getByText("Step 8 of 12: building and testing business numbers"),
    ).toBeTruthy();
  });

  test("unknown_eta", () => {
    renderHeader(run({ minutes_left: null }));
    expect(screen.getByText(/Working on it/)).toBeTruthy();
    expect(screen.getByText(/\$3\.80 so far/)).toBeTruthy();
    expect(screen.queryByText(/minutes left/)).toBeNull();
    expect(screen.queryByText(/hours left/)).toBeNull();
  });

  test("done shows the finished summary", () => {
    renderHeader(
      run({
        status: "done",
        percent: 100,
        finished_at: new Date(2026, 9, 27, 23, 0).toISOString(),
      }),
    );
    expect(screen.getByText("100%")).toBeTruthy();
    expect(screen.getByText("Finished")).toBeTruthy();
    expect(screen.getByText(/took 1 h 48 min/)).toBeTruthy();
    expect(screen.getByText(/All 12 steps done/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Review in Knowledge" })).toBeTruthy();
  });
});
