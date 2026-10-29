import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { emptyFeed, type AnswerBlock } from "@charie/shared";
import { LiveAnswer } from "./LiveAnswer";

afterEach(cleanup);

const BLOCKS: AnswerBlock[] = [
  { type: "reading", text: "I read this as sales." },
  {
    type: "text",
    paragraphs: [{ sentences: [{ kind: "fact", text: "Sales were $1.42M." }] }],
  },
];

function feedWith() {
  return { ...emptyFeed(), blocks: BLOCKS, texts: { 1: "Sales were $1.42M." } };
}

describe("LiveAnswer", () => {
  test("show_reading_false hides only the streamed reading line", () => {
    render(<LiveAnswer feed={feedWith()} onFollowUp={() => undefined} showReading={false} />);
    expect(screen.queryByText("I read this as sales.")).toBeNull();
    expect(screen.getByText("Sales were $1.42M.")).toBeTruthy();
  });

  test("show_reading defaults to showing the reading line", () => {
    render(<LiveAnswer feed={feedWith()} onFollowUp={() => undefined} />);
    expect(screen.getByText("I read this as sales.")).toBeTruthy();
    expect(screen.getByText("Sales were $1.42M.")).toBeTruthy();
  });
});
