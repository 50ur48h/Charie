import { afterEach, describe, expect, test } from "vitest";
import { designWorld, newWorld } from "./data";
import { initLearnerWorld, learner, resetLearnerMock, saveLearner } from "./state";

afterEach(() => {
  sessionStorage.clear();
});

describe("learner mock store", () => {
  test("starts with the design world", () => {
    resetLearnerMock("design");
    const world = learner();
    expect(world.documents).toHaveLength(14);
    expect(world.runs).toHaveLength(4);
    const reading = world.documents.find((doc) => doc.status === "reading");
    expect(reading?.progress).toBe(64);
    expect(world.runs[0]).toMatchObject({ kind: "refresh", status: "running", step: 8 });
  });

  test("?mock=new starts empty", () => {
    expect(initLearnerWorld("?mock=new")).toBe("new");
    expect(learner().documents).toHaveLength(0);
    expect(learner().runs).toHaveLength(0);
  });

  test("?mock=still starts the design world", () => {
    expect(initLearnerWorld("?mock=still")).toBe("still");
    expect(learner().documents).toHaveLength(14);
  });

  test("no mock value leaves the store alone", () => {
    resetLearnerMock("new");
    expect(initLearnerWorld("")).toBeNull();
    expect(learner().documents).toHaveLength(0);
  });

  test("keeps changes after saveLearner", () => {
    resetLearnerMock("design");
    learner().documents.pop();
    saveLearner();
    const saved = JSON.parse(sessionStorage.getItem("charie-learner-mock") as string) as {
      documents: unknown[];
    };
    expect(saved.documents).toHaveLength(13);
  });

  test("design world totals match the plan", () => {
    const world = designWorld();
    const pages = world.documents.reduce((sum, doc) => sum + (doc.pages ?? 0), 0);
    expect(pages).toBe(286);
    expect(newWorld()).toEqual({ documents: [], runs: [] });
  });
});
