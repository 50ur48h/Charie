import { afterEach, describe, expect, test } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { LearningRun, StepProgress } from "@charie/shared";
import { StepList } from "./StepList";

afterEach(() => {
  cleanup();
});

function run(progress: StepProgress[], status: LearningRun["status"]): LearningRun {
  return {
    id: 4,
    kind: "refresh",
    status,
    paused_by: null,
    reason: "3 new documents",
    step: 1,
    percent: 62,
    minutes_left: 25,
    progress,
    cost_usd: 3.8,
    summary: "6 changes",
    version_number: 15,
    new_version: true,
    started_at: new Date(2026, 9, 27, 21, 12).toISOString(),
    finished_at: null,
  };
}

describe("StepList", () => {
  test("a one-step run shows one step", () => {
    render(
      <StepList
        run={run([{ step: 1, done: 1, total: 1, note: "18 rules and hints" }], "running")}
      />,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("Read your notes")).toBeTruthy();
    expect(screen.queryByText("Study the database structure")).toBeNull();
  });

  test("a done run marks every actual step complete", () => {
    render(
      <StepList
        run={run(
          [
            { step: 1, done: 1, total: 1, note: "" },
            { step: 2, done: 3, total: 3, note: "" },
          ],
          "done",
        )}
      />,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
