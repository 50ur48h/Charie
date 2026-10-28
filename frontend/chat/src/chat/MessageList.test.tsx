import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import type { ChatMessage } from "@charie/shared";
import { MessageList } from "./MessageList";

afterEach(cleanup);

function userMessage(id: number, text: string): ChatMessage {
  return { id, role: "user", text, status: "done", mode: "thinking" };
}

function setMetrics(el: HTMLElement, scrollHeight: number, clientHeight: number): void {
  Object.defineProperties(el, {
    scrollHeight: { value: scrollHeight, configurable: true },
    clientHeight: { value: clientHeight, configurable: true },
  });
}

function list(messages: ChatMessage[]) {
  return <MessageList messages={messages} thinking={[]} thinkingSummary={null} />;
}

describe("MessageList", () => {
  test("follows new messages when the reader is at the bottom", () => {
    const { rerender } = render(list([userMessage(1, "First?")]));
    const messages = screen.getByTestId("messages");
    setMetrics(messages, 1000, 500);
    messages.scrollTop = 500;
    fireEvent.scroll(messages);

    setMetrics(messages, 1500, 500);
    rerender(list([userMessage(1, "First?"), userMessage(2, "Second?")]));

    expect(messages.scrollTop).toBe(1500);
    expect(screen.queryByRole("button", { name: "Jump to latest" })).toBeNull();
  });

  test("keeps the reader position and offers Jump to latest when scrolled up", () => {
    const { rerender } = render(list([userMessage(1, "First?")]));
    const messages = screen.getByTestId("messages");
    setMetrics(messages, 1000, 500);
    messages.scrollTop = 100;
    fireEvent.scroll(messages);

    setMetrics(messages, 1500, 500);
    rerender(list([userMessage(1, "First?"), userMessage(2, "Second?")]));

    expect(messages.scrollTop).toBe(100);
    const jump = screen.getByRole("button", { name: "Jump to latest" });
    fireEvent.click(jump);
    expect(messages.scrollTop).toBe(1500);
    expect(screen.queryByRole("button", { name: "Jump to latest" })).toBeNull();
  });
});
