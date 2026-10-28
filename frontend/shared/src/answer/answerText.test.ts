import { describe, expect, test } from "vitest";
import { answerText } from "./answerText";
import { sampleAnswer } from "../mocks/sampleChat";
import type { Answer } from "../api/chat-types";

describe("answerText", () => {
  test("blocks_to_plain_text", () => {
    const text = answerText(sampleAnswer(2));
    // Reading, prose and evidence cross over as readable lines.
    expect(text).toContain("I read this as");
    expect(text).toContain("October is a good month so far");
    expect(text).toContain("Sales change by restaurant");
    expect(text).toContain("Top restaurants");
    expect(text).toContain("How I worked this out");
    expect(text).toContain("SELECT");
    // Chart and table values cross over with their formatted labels.
    expect(text).toContain("Delivery orders per day");
    expect(text).toContain("Downtown");
  });

  test("omits_controls", () => {
    const answer: Answer = {
      message_id: 1,
      kb_version: 14,
      data_through: "2025-10-26",
      blocks: [
        { type: "reading", text: "I read this as trucks." },
        { type: "follow_ups", items: ["Same for last year?"] },
        {
          type: "method",
          definitions: [],
          steps: [],
          queries: [],
          sources: [],
        },
      ],
    };
    const text = answerText(answer);
    expect(text).toContain("I read this as trucks.");
    // Follow-up chips are UI buttons: their labels stay out of the copy.
    expect(text).not.toContain("Same for last year?");
    expect(text).not.toContain("You might also ask");
    // Control labels never enter text built from block data.
    expect(text).not.toContain("This is wrong");
    expect(text).not.toContain("All numbers checked");
    expect(text).not.toContain("Copy");
  });

  test("tree and kpi lines stay readable", () => {
    const answer: Answer = {
      message_id: 1,
      kb_version: 14,
      data_through: "2025-10-26",
      blocks: [
        {
          type: "kpis",
          items: [{ label: "Net sales", value: "$1.42M", change: "up 6.2%", compare: "Sep" }],
        },
        {
          type: "tree",
          title: "Why",
          nodes: [
            { id: "a", parent: null, label: "Outage" },
            { id: "b", parent: "a", label: "Downtown", value: "$17K" },
          ],
        },
      ],
    };
    expect(answerText(answer)).toBe(
      "Net sales: $1.42M (up 6.2% vs Sep)\n\nWhy\n- Outage\n  - Downtown ($17K)",
    );
  });
});
