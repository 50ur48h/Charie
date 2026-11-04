import { describe, expect, it } from "vitest";

import { modelName } from "@/lib/models";

import { sentence } from "./trace";

function call(payload: Record<string, unknown>) {
  return sentence({ seq: 1, type: "model_called", payload, ts: "2026-11-04T00:00:00Z" });
}

describe("live Meta model calls in the trace", () => {
  it("names the model, what it did, and the live call behind it", () => {
    const step = call({
      model: "muse-spark-1.3",
      role: "plan",
      latency_ms: 2400,
      input_tokens: 3120,
      output_tokens: 410,
      status: "ok",
    });

    expect(step.lead).toBe("Muse Spark 1.3 planned the checks");
    expect(step.rest).toBe(
      "Live call to the Meta Model API (muse-spark-1.3) · 2.4 s · 3,120 tokens in, 410 out.",
    );
  });

  it("says when a call failed, and why", () => {
    const step = call({ model: "muse-wonder-1.0", role: "sql", status: "error", error: "rate limited" });

    expect(step.lead).toBe("Muse Wonder 1.0 call failed");
    expect(step.rest).toBe("Meta Model API (muse-wonder-1.0) — rate limited");
  });

  it("turns a model id into the name people know", () => {
    expect(modelName("muse-spark-1.3")).toBe("Muse Spark 1.3");
    expect(modelName("muse-wonder-1.0")).toBe("Muse Wonder 1.0");
  });
});
