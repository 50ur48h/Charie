// The still-learning card on the New chat page (P12.1).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { StillLearning } from "./StillLearning";

afterEach(() => {
  cleanup();
});

const LEARNER_URL = "http://localhost:5174";

describe("StillLearning", () => {
  test("shows progress while learning", () => {
    render(
      <StillLearning
        learning={{ status: "running", step_title: "Read your documents", percent: 38 }}
        learnerUrl={LEARNER_URL}
      />,
    );
    expect(screen.getByText("Charie is still learning")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Learning progress: 38 percent" })).toBeTruthy();
    expect(screen.getByText("38% · Read your documents")).toBeTruthy();
  });

  test("shows not started", () => {
    render(
      <StillLearning learning={{ status: "none", step_title: null, percent: 0 }} learnerUrl={LEARNER_URL} />,
    );
    expect(screen.getByText("Learning hasn't started yet.")).toBeTruthy();
  });

  test("shows the failed text", () => {
    render(
      <StillLearning learning={{ status: "failed", step_title: "Self-test", percent: 80 }} learnerUrl={LEARNER_URL} />,
    );
    expect(
      screen.getByText("The last learning run stopped with a problem. Open the Learner to see what happened."),
    ).toBeTruthy();
  });

  test("shows the publish text when learning is done", () => {
    render(
      <StillLearning learning={{ status: "done", step_title: "Self-test", percent: 100 }} learnerUrl={LEARNER_URL} />,
    );
    expect(
      screen.getByText("Learning is done. Publish the first version in the Learner to start."),
    ).toBeTruthy();
  });

  test("Open Learner uses learner_url", () => {
    render(
      <StillLearning learning={{ status: "done", step_title: "Self-test", percent: 100 }} learnerUrl={LEARNER_URL} />,
    );
    const link = screen.getByRole("link", { name: "Open Learner" });
    expect(link.getAttribute("href")).toBe(LEARNER_URL);
    expect(link.getAttribute("target")).toBe("_blank");
  });
});
