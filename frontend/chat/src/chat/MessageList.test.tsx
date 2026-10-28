import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import type { ChatMessage, ThinkingStatus } from "@charie/shared";
import { MessageList } from "./MessageList";

afterEach(cleanup);

function userMessage(id: number, text: string): ChatMessage {
  return { id, role: "user", text, status: "done", started_at: "2026-10-28T08:00:00.000Z" };
}

function assistantMessage(
  id: number,
  status: "done" | "thinking",
  thinking: { seq: number; title: string }[],
): ChatMessage {
  return {
    id,
    role: "assistant",
    status,
    mode: "thinking",
    answer: null,
    thinking: thinking.map((line) => ({
      ...line,
      kind: "step" as const,
      // Line states are running/done/failed; only messages are "thinking".
      status: (status === "thinking" ? "running" : "done") as ThinkingStatus,
      at: "2025-10-26T12:00:00Z",
    })),
    summary: null,
  };
}

function setMetrics(el: HTMLElement, scrollHeight: number, clientHeight: number): void {
  Object.defineProperties(el, {
    scrollHeight: { value: scrollHeight, configurable: true },
    clientHeight: { value: clientHeight, configurable: true },
  });
}

describe("MessageList", () => {
  test("follows new messages when the reader is at the bottom", () => {
    const { rerender } = render(<MessageList messages={[userMessage(1, "First?")]} />);
    const messages = screen.getByTestId("messages");
    setMetrics(messages, 1000, 500);
    messages.scrollTop = 500;
    fireEvent.scroll(messages);

    setMetrics(messages, 1500, 500);
    rerender(<MessageList messages={[userMessage(1, "First?"), userMessage(2, "Second?")]} />);

    expect(messages.scrollTop).toBe(1500);
    expect(screen.queryByRole("button", { name: "Jump to latest" })).toBeNull();
  });

  test("keeps the reader position and offers Jump to latest when scrolled up", () => {
    const { rerender } = render(<MessageList messages={[userMessage(1, "First?")]} />);
    const messages = screen.getByTestId("messages");
    setMetrics(messages, 1000, 500);
    messages.scrollTop = 100;
    fireEvent.scroll(messages);

    setMetrics(messages, 1500, 500);
    rerender(<MessageList messages={[userMessage(1, "First?"), userMessage(2, "Second?")]} />);

    expect(messages.scrollTop).toBe(100);
    const jump = screen.getByRole("button", { name: "Jump to latest" });
    fireEvent.click(jump);
    expect(messages.scrollTop).toBe(1500);
    expect(screen.queryByRole("button", { name: "Jump to latest" })).toBeNull();
  });

  test("each answer keeps its own thinking panel", () => {
    render(
      <MessageList
        messages={[
          userMessage(1, "First?"),
          assistantMessage(2, "done", [{ seq: 1, title: "First evidence" }]),
          userMessage(3, "Second?"),
          assistantMessage(4, "thinking", [{ seq: 1, title: "Second evidence" }]),
        ]}
      />,
    );
    // One panel per answer: the running one starts open, the finished one shut.
    expect(screen.getAllByRole("button", { name: /Thinking/ })).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Second evidence/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /First evidence/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Thinking" }));
    expect(screen.getByRole("button", { name: /First evidence/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Second evidence/ })).toBeTruthy();
  });
});
