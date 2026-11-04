import { describe, expect, it } from "vitest";

import { STEP_SENTENCES, sentence } from "./trace";

/** Every step reads as a sentence, including when the payload is empty. */

/** Punctuation and space only — what a broken template leaves behind. */
const ONLY_PUNCTUATION = /^[\s.,;:—–-]*$/;

const ENTRIES = Object.entries(STEP_SENTENCES);

/** One builder by name, or a failure that says which name was missing. */
function build(type: string, payload: Record<string, unknown> = {}) {
  const make = STEP_SENTENCES[type];
  if (!make) throw new Error(`STEP_SENTENCES has no entry for ${type}`);
  return make(payload);
}

describe("every step's sentence survives an empty payload", () => {
  it("covers more than a handful of event types, so the sweep means something", () => {
    // Guards the sweep itself: an import that silently resolved to `{}` would make every test...
    expect(ENTRIES.length).toBeGreaterThan(15);
  });

  it.each(ENTRIES)("%s says something, and never only punctuation", (_type, make) => {
    const { lead, rest } = make({});

    expect(lead.trim().length).toBeGreaterThan(0);
    // `rest` is allowed to be empty — that is the honest outcome when an event carries nothing...
    if (rest !== "") {
      expect(rest).not.toMatch(ONLY_PUNCTUATION);
    }
  });

  it.each(ENTRIES)("%s never leaks a missing value into the prose", (_type, make) => {
    const { lead, rest } = make({});
    const whole = `${lead} ${rest}`;

    expect(whole).not.toContain("undefined");
    expect(whole).not.toContain("null");
    expect(whole).not.toContain("NaN");
    expect(whole).not.toContain("[object Object]");
  });
});

describe("the sentences use what the events carry", () => {
  it("counts in words, and never says '1 rows'", () => {
    expect(build("query_executed", { row_count: 1, duration_ms: 4 }).rest).toContain(
      "1 row came back",
    );
    expect(build("query_executed", { row_count: 2, duration_ms: 4 }).rest).toContain(
      "2 rows came back",
    );
  });

  it("says why a join was checked, not just that it was", () => {
    // The event carries `answerable`; the sentence carries the consequence.
    expect(build("capability_checked", { answerable: true }).rest).toContain("they can");

    const refused = build("capability_checked", { answerable: false, unreachable: ["a and b"] });
    expect(refused.rest).toContain("cannot");
    expect(refused.rest).toContain("invent rows");
  });

  it("reads a run's totals, which nothing rendered before", () => {
    const step = build("run_finished", { totals: { queries: 1, llm_calls: 4 } });

    expect(step.rest).toContain("1 query");
    expect(step.rest).toContain("4 model calls");
  });

  it("keeps a step number of zero rather than dropping it as falsy", () => {
    // `num` returns a number and `0` is falsy in TypeScript.
    expect(build("step_started", { iteration: 0 }).rest).toContain("step 0");
    expect(build("step_started").rest).toBe("");
  });
});

describe("an event this build has never heard of", () => {
  it("shows its raw name rather than being hidden", () => {
    // The module's standing rule: a trace that silently omits a step is worse than an ugly one.
    const step = sentence({
      seq: 1,
      type: "something_new",
      payload: {},
    } as unknown as Parameters<typeof sentence>[0]);

    expect(step.lead).toBe("something_new");
    expect(step.rest).toBe("");
  });
});

describe("the period check is legible, including when it could not run", () => {
  // B-157, D-059.

  it("says both periods when the answer is outside what the catalogue records", () => {
    const step = build("answer_composed", {
      limitations: 1,
      coverage: {
        status: "outside",
        reason: "",
        answered: "2023-01 to 2024-12",
        available: "2025-01 to 2025-12",
      },
    });

    expect(step.rest).toContain("2023-01 to 2024-12");
    expect(step.rest).toContain("2025-01 to 2025-12");
  });

  it("says the answer sat inside the period when it did", () => {
    const step = build("answer_composed", {
      limitations: 0,
      coverage: {
        status: "contained",
        reason: "",
        answered: "2025-12",
        available: "2025-01 to 2025-12",
      },
    });

    expect(step.rest).toContain("inside the period");
  });

  it("says why it could not look, rather than saying nothing", () => {
    const step = build("answer_composed", {
      limitations: 0,
      coverage: {
        status: "abstained",
        reason: "the result was cut off at the row limit",
        answered: null,
        available: null,
      },
    });

    expect(step.rest).toContain("could not be checked");
    expect(step.rest).toContain("row limit");
  });

  it("is silent when the payload carries no coverage at all", () => {
    // `coverage: null` is what an older server sends.
    expect(build("answer_composed", { limitations: 0, coverage: null }).rest).not.toContain(
      "period",
    );
    expect(build("answer_composed", { limitations: 0 }).rest).not.toContain("period");
  });
});

describe("the trace spends what the events already carry", () => {
  // WP13.21.

  it("says how much of each table the model actually saw", () => {
    // B-160. "25 tables" said nothing about detail.
    const step = build("context_selected", {
      tables: ["public.fact_sale", "public.dim_outlet", "public.dim_calendar"],
      tables_in_full: 1,
      tables_in_outline: 2,
      tables_dropped: 0,
    });

    expect(step.rest).toContain("1 in full and 2 in outline");
  });

  it("says when a table matched and would not fit", () => {
    const step = build("context_selected", {
      tables: ["public.fact_sale"],
      tables_in_full: 1,
      tables_in_outline: 0,
      tables_dropped: 3,
    });

    expect(step.rest).toContain("3 tables matched but would not fit");
  });

  it("says when the thread chose the tables rather than the question", () => {
    const step = build("context_selected", {
      tables: ["public.fact_sale"],
      tables_found_via: "thread",
    });

    expect(step.rest).toContain("named no table of its own");
  });

  it("says how many tables were found by meaning rather than by wording", () => {
    const step = build("context_selected", {
      tables: ["public.fact_sale", "public.dim_outlet"],
      tables_found_by: { "public.fact_sale": "vector", "public.dim_outlet": "lexical" },
    });

    expect(step.rest).toContain("1 of them was found by meaning");
  });

  it("tells no definitions matched apart from having no definitions", () => {
    // B-087's finding, said out loud.
    const none = build("context_selected", {
      tables: ["public.fact_sale"],
      definitions_applied: [],
      definitions_available: 18,
    });
    const some = build("context_selected", {
      tables: ["public.fact_sale"],
      definitions_applied: ["net revenue"],
      definitions_available: 18,
    });

    expect(none.rest).toContain("None of your 18 definitions matched");
    expect(some.rest).toContain("1 of your 18 definitions applied");
  });

  it("mentions restricted columns and earlier turns when there are any", () => {
    const step = build("context_selected", {
      tables: ["public.fact_sale"],
      restrictions: 2,
      history_turns: 3,
    });

    expect(step.rest).toContain("2 columns are restricted");
    expect(step.rest).toContain("3 earlier turns");
  });

  it("stays quiet about every count that is zero", () => {
    // A sentence for each absent thing is how a reader learns to skip the panel.
    const step = build("context_selected", {
      tables: ["public.fact_sale"],
      tables_dropped: 0,
      restrictions: 0,
      history_turns: 0,
      definitions_available: 0,
    });

    expect(step.rest).not.toContain("would not fit");
    expect(step.rest).not.toContain("restricted");
    expect(step.rest).not.toContain("earlier turn");
    expect(step.rest).not.toContain("definitions");
  });

  it("names what the capability check ruled out, not only that it ran", () => {
    const step = build("capability_checked", {
      answerable: true,
      unreachable: ["fact_sale ↔ fact_purchase"],
    });

    expect(step.rest).toContain("Ruled out joining");
    expect(step.rest).toContain("fact_sale ↔ fact_purchase");
  });

  it("says which pairs can only be compared, not joined", () => {
    const step = build("capability_checked", {
      answerable: true,
      comparable: ["fact_sale ↔ fact_purchase via dim_business"],
    });

    expect(step.rest).toContain("compared side by side");
  });

  it("tells an unprofiled source apart from a checked one", () => {
    // B-157/D-059: the key is present even when null, and the two must not read the same.
    const known = build("capability_checked", {
      answerable: true,
      available_period: "2025-01 to 2025-12",
    });
    const unknown = build("capability_checked", { answerable: true, available_period: null });
    const absent = build("capability_checked", { answerable: true });

    expect(known.rest).toContain("2025-01 to 2025-12");
    expect(unknown.rest).toContain("has been profiled");
    expect(absent.rest).not.toContain("profiled");
  });
});
