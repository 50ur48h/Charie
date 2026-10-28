import { describe, expect, test } from "vitest";
import {
  emptyThinking,
  updateThinking,
  type ThinkingLine,
} from "./thinking";

function line(seq: number, title: string): ThinkingLine {
  return { seq, kind: "query", status: "running", title, at: "2025-10-26T12:00:00Z" };
}

describe("thinking", () => {
  test("a repeated seq updates the same row instead of adding one", () => {
    let state = updateThinking(emptyThinking(), { type: "line", line: line(1, "Reading") });
    state = updateThinking(state, {
      type: "line",
      line: { seq: 1, kind: "query", status: "done", title: "Read the sales", at: "2025-10-26T12:00:00Z" },
    });
    expect(state.lines).toHaveLength(1);
    expect(state.lines[0]).toMatchObject({ seq: 1, status: "done", title: "Read the sales" });
  });

  test("lines keep arrival order, not seq order", () => {
    let state = emptyThinking();
    state = updateThinking(state, { type: "line", line: line(3, "Third") });
    state = updateThinking(state, { type: "line", line: line(1, "First") });
    expect(state.lines.map((item) => item.seq)).toEqual([3, 1]);
  });

  test("a summary lands without touching the lines", () => {
    let state = updateThinking(emptyThinking(), { type: "line", line: line(1, "Reading") });
    state = updateThinking(state, {
      type: "summary",
      summary: { seconds: 38, steps: 8, queries: 4, documents: 1 },
    });
    expect(state.summary).toEqual({ seconds: 38, steps: 8, queries: 4, documents: 1 });
    expect(state.lines).toHaveLength(1);
  });
});
