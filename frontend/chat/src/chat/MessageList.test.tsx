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

describe("MessageList", () => {
  test("follows new messages when the reader is at the bottom", () => {
    const { rerender } = render(<MessageList messages={[userMessage(1, "First?")]} />);
    const list = screen.getByTestId("messages");
    setMetrics(list, 1000, 500);
    list.scrollTop = 500;
    fireEvent.scroll(list);

    setMetrics(list, 1500, 500);
    rerender(<MessageList messages={[userMessage(1, "First?"), userMessage(2, "Second?")]} />);

    expect(list.scrollTop).toBe(1500);
    expect(screen.queryByRole("button", { name: "Jump to latest" })).toBeNull();
  });

  test("keeps the reader position and offers Jump to latest when scrolled up", () => {
    const { rerender } = render(<MessageList messages={[userMessage(1, "First?")]} />);
    const list = screen.getByTestId("messages");
    setMetrics(list, 1000, 500);
    list.scrollTop = 100;
    fireEvent.scroll(list);

    setMetrics(list, 1500, 500);
    rerender(<MessageList messages={[userMessage(1, "First?"), userMessage(2, "Second?")]} />);

    expect(list.scrollTop).toBe(100);
    const jump = screen.getByRole("button", { name: "Jump to latest" });
    fireEvent.click(jump);
    expect(list.scrollTop).toBe(1500);
    expect(screen.queryByRole("button", { name: "Jump to latest" })).toBeNull();
  });
});
