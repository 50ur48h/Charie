import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { Answer, AnswerBlock } from "../api/chat-types";
import { AnswerView } from "./AnswerView";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function answerWith(blocks: AnswerBlock[]): Answer {
  return { message_id: 2, kb_version: 14, data_through: "2025-10-26", blocks };
}

describe("AnswerView", () => {
  test("text_plus_method starts open; anything else starts closed", () => {
    const method: AnswerBlock = {
      type: "method",
      definitions: ["Sales mean delivered orders."],
      steps: ["Added up December."],
      queries: [],
      sources: [],
    };
    const text: AnswerBlock = {
      type: "text",
      paragraphs: [{ sentences: [{ kind: "note", text: "Here is how." }] }],
    };
    const { unmount } = render(
      <AnswerView answer={answerWith([text, method])} onFollowUp={() => undefined} />,
    );
    expect(
      screen.getByRole("button", { name: /What this means/ }).getAttribute("aria-expanded"),
    ).toBe("true");
    unmount();
    render(
      <AnswerView
        answer={answerWith([text, method, { type: "follow_ups", items: ["Why?"] }])}
        onFollowUp={() => undefined}
      />,
    );
    expect(
      screen.getByRole("button", { name: /What this means/ }).getAttribute("aria-expanded"),
    ).toBe("false");
  });

  test("ordered_repeated_blocks keep their order and all render", () => {
    render(
      <AnswerView
        answer={answerWith([
          { type: "reading", text: "I read this as sales." },
          {
            type: "callout",
            tone: "note",
            text: "October has data up to the 26th only.",
          },
          {
            type: "text",
            paragraphs: [{ sentences: [{ kind: "fact", text: "Sales were $1.42M." }] }],
          },
          {
            type: "text",
            paragraphs: [{ sentences: [{ kind: "note", text: "October is partial." }] }],
          },
          {
            type: "suggestions",
            title: "What I'd do",
            items: [{ text: "Check Downtown.", confidence: "likely" }],
          },
          { type: "follow_ups", items: ["Same for last year?"] },
        ])}
        onFollowUp={() => undefined}
      />,
    );
    const order = [
      "I read this as sales.",
      "October has data up to the 26th only.",
      "Sales were $1.42M.",
      "October is partial.",
      "What I'd do",
      "Check Downtown.",
      "Same for last year?",
    ];
    let lastIndex = -1;
    for (const text of order) {
      const index = document.body.innerHTML.indexOf(text);
      expect(index).toBeGreaterThan(lastIndex);
      lastIndex = index;
    }
    // Confidence shows verbatim and is never reinterpreted.
    expect(screen.getByText("· likely")).toBeTruthy();
  });

  test("reading_setting hides only the reading line", () => {
    render(
      <AnswerView
        answer={answerWith([
          { type: "reading", text: "I read this as sales." },
          {
            type: "text",
            paragraphs: [{ sentences: [{ kind: "fact", text: "Sales were $1.42M." }] }],
          },
        ])}
        onFollowUp={() => undefined}
        showReading={false}
      />,
    );
    expect(screen.queryByText("I read this as sales.")).toBeNull();
    expect(screen.getByText("Sales were $1.42M.", { exact: false })).toBeTruthy();
  });

  test("followup_fills_composer through its callback", () => {
    const onFollowUp = vi.fn();
    render(
      <AnswerView
        answer={answerWith([{ type: "follow_ups", items: ["How much did it cost?"] }])}
        onFollowUp={onFollowUp}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /How much did it cost\?/ }));
    expect(onFollowUp).toHaveBeenCalledWith("How much did it cost?");
  });

  test("renders every sentence kind as sent, with a hover hint on possible reasons", () => {
    render(
      <AnswerView
        answer={answerWith([
          {
            type: "text",
            paragraphs: [
              {
                sentences: [
                  { kind: "fact", text: "Sales were $1.42M." },
                  { kind: "conclusion", text: "We are ahead." },
                  { kind: "possible_reason", text: "The holiday menu." },
                  { kind: "suggestion", text: "Keep it." },
                  { kind: "note", text: "October is partial." },
                ],
              },
            ],
          },
        ])}
        onFollowUp={() => undefined}
      />,
    );
    expect(screen.getByText("Sales were $1.42M.", { exact: false })).toBeTruthy();
    expect(screen.getByText("We are ahead.", { exact: false })).toBeTruthy();
    expect(screen.getByText("The holiday menu.", { exact: false })).toBeTruthy();
    expect(screen.getByText("Keep it.", { exact: false })).toBeTruthy();
    expect(screen.getByText("October is partial.", { exact: false })).toBeTruthy();
    // No injected prefixes: kinds look the same, except the possible
    // reason carries its hover hint.
    expect(screen.queryByText(/Maybe:|Try:/)).toBeNull();
    const reason = screen
      .getByText("The holiday menu.", { exact: false })
      .closest("span");
    expect(reason?.getAttribute("title")).toBe("possible reason");
  });

  test("an unknown block warns and falls back", () => {
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <AnswerView
        answer={answerWith([{ type: "nope" } as unknown as AnswerBlock])}
        onFollowUp={() => undefined}
      />,
    );
    expect(screen.getByText("Unsupported block.")).toBeTruthy();
    expect(error).toHaveBeenCalledWith("Unsupported answer block: nope");
  });
});
