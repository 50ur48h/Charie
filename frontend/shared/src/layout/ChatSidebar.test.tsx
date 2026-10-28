import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { ChatSidebar } from "./ChatSidebar";

afterEach(cleanup);

const GROUPS = [
  { label: "Today", chats: [{ id: 1, title: "How are we doing?" }] },
  { chats: [{ id: 2, title: "Unlabeled group chat" }] },
];

function hrefOf(name: string): string | null {
  return screen.getByRole("link", { name }).getAttribute("href");
}

function currentOf(name: string): string | null {
  return screen.getByRole("link", { name }).getAttribute("aria-current");
}

describe("ChatSidebar", () => {
  test("shows the links and the chat groups", () => {
    render(
      <ChatSidebar
        active="usage"
        activeChatId={1}
        chats={{ status: "ready", groups: GROUPS }}
        questionCount={3}
        user={{ name: "Sourabh", detail: "Bella Forno Group" }}
      />,
    );
    expect(hrefOf("Charie")).toBe("/");
    expect(hrefOf("New chat")).toBe("/");
    expect(
      screen.getByRole("link", { name: "Questions for you 3 waiting" }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Knowledge" })).toBeTruthy();
    expect(screen.getByText("Today")).toBeTruthy();
    expect(hrefOf("How are we doing?")).toBe("/chat/1");
    expect(screen.getByRole("link", { name: "Unlabeled group chat" })).toBeTruthy();
    expect(screen.getByText("Sourabh")).toBeTruthy();
  });

  test("marks the active page and chat", () => {
    render(
      <ChatSidebar
        active="usage"
        activeChatId={1}
        chats={{ status: "ready", groups: GROUPS }}
      />,
    );
    expect(currentOf("Usage")).toBe("page");
    expect(currentOf("How are we doing?")).toBe("page");
    expect(currentOf("Settings")).toBeNull();
  });

  test("shows the questions badge only above zero", () => {
    const { rerender } = render(
      <ChatSidebar chats={{ status: "ready", groups: [] }} questionCount={3} />,
    );
    expect(screen.getByText("waiting")).toBeTruthy();
    rerender(<ChatSidebar chats={{ status: "ready", groups: [] }} questionCount={0} />);
    expect(screen.queryByText("waiting")).toBeNull();
  });

  test("shows the loading, error and empty chat lists", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ChatSidebar chats={{ status: "loading" }} />);
    expect(document.querySelectorAll("[aria-hidden='true']").length).toBeGreaterThan(0);
    const onRetry = vi.fn();
    rerender(<ChatSidebar chats={{ status: "error", onRetry }} />);
    expect(screen.getByText("Couldn't load your chats.")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    rerender(<ChatSidebar chats={{ status: "ready", groups: [] }} />);
    expect(screen.getByText("No chats yet.")).toBeTruthy();
  });

  test("the hide button calls onHide", async () => {
    const user = userEvent.setup();
    const onHide = vi.fn();
    render(<ChatSidebar chats={{ status: "ready", groups: [] }} onHide={onHide} />);
    await user.click(screen.getByRole("button", { name: "Hide sidebar" }));
    expect(onHide).toHaveBeenCalledTimes(1);
  });

  test("has no hide button without onHide", () => {
    render(<ChatSidebar chats={{ status: "ready", groups: [] }} />);
    expect(screen.queryByRole("button", { name: "Hide sidebar" })).toBeNull();
  });
});
