import { describe, expect, test } from "vitest";
import type { AssistantMessage } from "../api/chat-types";
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

function assistantOf(chatId: number, index: number): AssistantMessage {
  const message = getMockChat(chatId)?.messages[index];
  if (message?.role !== "assistant") throw new Error(`message ${index} is not an answer`);
  return message;
}

describe("sample chat", () => {
  test("the sample answer covers every block variant", () => {
    const answer = sampleAnswer(2);
    expect(answer.blocks.map((block) => block.type)).toEqual([
      "reading",
      "text",
      "kpis",
      "chart",
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
      "done",
      "done",
    ]);
    expect(assistantOf(1, 1).answer?.blocks).toHaveLength(11);
    // Each answer keeps its own panel: the follow-up's evidence differs.
    expect(assistantOf(1, 1).thinking.map((line) => line.title)).toEqual([
      "Understood the question",
      "Added up sales by restaurant",
      "Read the incident log",
      "Found the Downtown outage",
      "Checked every number",
    ]);
    expect(assistantOf(1, 3).thinking.map((line) => line.title)).toEqual([
      "Understood the follow-up",
      "Adding up last year's sales",
    ]);
    expect(assistantOf(1, 3).summary).toEqual({
      seconds: 21,
      steps: 5,
      queries: 2,
      documents: 0,
    });

    const thinking = getMockChat(2);
    expect(thinking?.messages.map((message) => message.status)).toEqual([
      "done",
      "thinking",
    ]);
    expect(assistantOf(2, 1).summary).toBeNull();

    expect(getMockChat(3)?.messages).toEqual([]);

    const failed = getMockChat(4);
    expect(failed?.messages.map((message) => message.status)).toEqual([
      "done",
      "failed",
    ]);
    expect(assistantOf(4, 1).thinking.map((line) => line.status)).toEqual([
      "done",
      "failed",
    ]);
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
    expect(assistantOf(2, 1).thinking.map((line) => line.status)).toEqual([
      "done",
      "done",
    ]);
    expect(finishMockMessage(999)).toBe(false);
    expect(listMockChats()).toHaveLength(8);
  });
});
