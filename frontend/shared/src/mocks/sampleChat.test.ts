import { describe, expect, test } from "vitest";
import {
  addMockMessage,
  createMockChat,
  getMockChat,
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
});
