import { describe, expect, test, vi } from "vitest";
import { applyFeedEvent, emptyFeed } from "./message-feed";

function event(id: string | null, name: string, data: unknown) {
  return { id, event: name, data };
}

describe("message feed", () => {
  test("duplicate_id applies once", () => {
    let feed = emptyFeed();
    feed = applyFeedEvent(feed, event("3", "text", { index: 0, delta: "Hello " }));
    feed = applyFeedEvent(feed, event("3", "text", { index: 0, delta: "Hello " }));
    expect(feed.texts[0]).toBe("Hello ");
  });

  test("same_seq updates the thinking line", () => {
    let feed = emptyFeed();
    feed = applyFeedEvent(
      feed,
      event("1", "thinking", { seq: 1, kind: "step", status: "running", title: "Reading", at: "t" }),
    );
    feed = applyFeedEvent(
      feed,
      event("2", "thinking", { seq: 1, kind: "step", status: "done", title: "Reading", at: "t" }),
    );
    expect(feed.thinking.lines).toHaveLength(1);
    expect(feed.thinking.lines[0].status).toBe("done");
  });

  test("terminal_reload keeps the first done", () => {
    let feed = emptyFeed();
    feed = applyFeedEvent(feed, event("9", "done", { message_id: 8, status: "done" }));
    feed = applyFeedEvent(feed, event("10", "done", { message_id: 8, status: "done" }));
    expect(feed.done).toEqual({ message_id: 8, status: "done" });
  });

  test("unknown events and bad data warn without crashing", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    let feed = emptyFeed();
    feed = applyFeedEvent(feed, event("1", "mystery", {}));
    feed = applyFeedEvent(feed, event(null, "text", { index: "zero" }));
    feed = applyFeedEvent(feed, event(null, "block", { index: 0, block: 42 }));
    expect(feed.blocks).toEqual([]);
    expect(feed.texts).toEqual({});
    expect(warn).toHaveBeenCalledTimes(3);
    warn.mockRestore();
  });

  test("text buffers select by block index", () => {
    let feed = emptyFeed();
    feed = applyFeedEvent(feed, event("1", "text", { index: 2, delta: "a " }));
    feed = applyFeedEvent(feed, event("2", "text", { index: 0, delta: "b" }));
    expect(feed.texts).toEqual({ 2: "a ", 0: "b" });
  });
});
