import { describe, expect, test } from "vitest";
import {
  addMockMessage,
  createMockChat,
  finishMockMessage,
  forgetMockChats,
  getMockChat,
  listMockChats,
  resetMockChats,
  sampleAnswer,
} from "./sampleChat";

describe("sample chat", () => {
  test("the sample answer covers every block variant", () => {
    const answer = sampleAnswer(2);
    expect(answer.blocks.map((block) => block.type)).toEqual([
      "reading",
      "text",
      "kpis",
      "chart",
      "table",
      "tree",
      "callout",
      "suggestions",
      "method",
      "follow_ups",
    ]);
  });

  test("seed chats are finished, thinking and fresh", () => {
    const finished = getMockChat(1);
    expect(finished?.messages.map((message) => message.status)).toEqual([
      "done",
      "done",
    ]);
    expect(finished?.messages[1]?.answer?.blocks).toHaveLength(10);

    const thinking = getMockChat(2);
    expect(thinking?.messages.map((message) => message.status)).toEqual([
      "done",
      "thinking",
    ]);

    expect(getMockChat(3)?.messages).toEqual([]);

    const failed = getMockChat(4);
    expect(failed?.messages.map((message) => message.status)).toEqual([
      "done",
      "failed",
    ]);
    expect(failed?.thinking.map((line) => line.status)).toEqual(["done", "failed"]);
    expect(getMockChat(999)).toBeUndefined();
  });

  test("a created chat takes its title from the first question", () => {
    resetMockChats();
    const chat = createMockChat();
    expect(chat.title).toBe("New chat");
    const sent = addMockMessage(chat.id, "Why did delivery drop?");
    expect(sent).toMatchObject({ user_message_id: 1000, assistant_message_id: 1001 });
    const detail = getMockChat(chat.id);
    expect(detail?.title).toBe("Why did delivery drop?");
    expect(detail?.messages.map((message) => message.role)).toEqual([
      "user",
      "assistant",
    ]);
    expect(addMockMessage(999, "nope")).toBeUndefined();
  });

  test("created chats, messages and stops survive a reload", () => {
    resetMockChats();
    const chat = createMockChat();
    addMockMessage(chat.id, "Hello?");
    finishMockMessage(1001);
    forgetMockChats();
    const detail = getMockChat(chat.id);
    expect(detail?.title).toBe("Hello?");
    expect(detail?.messages.map((message) => message.status)).toEqual([
      "done",
      "stopped",
    ]);
    expect(listMockChats()).toHaveLength(9);
  });

  test("finishing stops the running answer without duplicating the list", () => {
    resetMockChats();
    expect(finishMockMessage(4)).toBe(true);
    expect(getMockChat(2)?.messages[1]?.status).toBe("stopped");
    expect(finishMockMessage(999)).toBe(false);
    expect(listMockChats()).toHaveLength(8);
  });
});
