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
  test("final_snapshot_replaces_buffer", () => {
    let feed = emptyFeed();
    feed = applyFeedEvent(feed, event("48", "block", { index: 0, block: { type: "text", paragraphs: [] } }));
    feed = applyFeedEvent(feed, event("49", "text", { index: 0, delta: "Net sa" }));
    expect(feed.texts[0]).toBe("Net sa");
    feed = applyFeedEvent(feed, event("0", "reset", { message_id: 8 }));
    expect(feed.texts).toEqual({});
    expect(feed.blocks).toEqual([]);
    expect(feed.done).toBeNull();
    feed = applyFeedEvent(
      feed,
      event("1", "thinking", { seq: 1, kind: "step", status: "done", title: "Reading", at: "t" }),
    );
    feed = applyFeedEvent(feed, event("2", "summary", { seconds: 4, steps: 9, queries: 1, documents: 0 }));
    feed = applyFeedEvent(feed, event("3", "done", { message_id: 8, status: "done" }));
    expect(feed.done).toEqual({ message_id: 8, status: "done" });
    // The stale live cursor no longer suppresses the fresh numbering.
    expect(feed.thinking.lines).toHaveLength(1);
  });

  test("no_raw_labels", () => {
    let feed = emptyFeed();
    feed = applyFeedEvent(feed, event("1", "block", { index: 0, block: { type: "text", paragraphs: [] } }));
    feed = applyFeedEvent(feed, event("2", "text", { index: 0, delta: "Net sales " }));
    feed = applyFeedEvent(feed, event("3", "text", { index: 0, delta: "were " }));
    feed = applyFeedEvent(feed, event("4", "text", { index: 0, delta: "$359.00." }));
    expect(feed.texts[0]).toBe("Net sales were $359.00.");
    expect(feed.texts[0]).not.toMatch(/\[[ntqp]\d+\]/);
  });
});
