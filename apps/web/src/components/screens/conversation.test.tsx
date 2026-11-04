import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConversationThread, isNumeric, nearlyOut, progressLine } from "./conversation";

const session = {
  mode: "dev" as const,
  who: "alice",
  getToken: async () => "token",
  signIn: async () => undefined,
  signOut: async () => undefined,
  problems: [],
  busy: false,
  error: null,
};

vi.mock("@/lib/auth/session", () => ({
  useSession: () => session,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/orgs/o1/conversations/c1",
}));

const CONVERSATION = {
  id: "c1",
  title: "How many orders were placed in July 2026?",
  created_at: "2026-08-15T09:00:00Z",
  message_count: 2,
  last_run_id: "r1",
  data_source_id: "d1",
  data_source_name: "Pizza (PostgreSQL)",
};

const MESSAGES = [
  {
    id: "m1",
    role: "user",
    content: "How many orders were placed in July 2026?",
    run_id: "r1",
    created_at: "2026-08-15T09:00:00Z",
  },
  {
    id: "m2",
    role: "assistant",
    content: "6,214 orders were placed in July 2026.",
    run_id: "r1",
    created_at: "2026-08-15T09:00:20Z",
  },
];

const ANSWERED = {
  id: "r1",
  conversation_id: "c1",
  status: "completed",
  question: "How many orders were placed in July 2026?",
  answer: "6,214 orders were placed in July 2026.",
  findings: [
    {
      id: "f1",
      statement: "6,214 orders were placed in July 2026.",
      support: ["x1"],
      confidence: "high",
    },
  ],
  started_at: "2026-08-15T09:00:01Z",
  finished_at: "2026-08-15T09:00:20Z",
  failure_reason: null,
};

const EXECUTION = {
  id: "x1",
  run_id: "r1",
  status: "ok",
  sql: 'SELECT count(*) AS "order_count" FROM "public"."orders"',
  tables: ["public.orders"],
  columns: ["order_count"],
  row_count: 1,
  duration_ms: 31,
  violation_code: null,
  error: null,
  sensitive_accessed: false,
  masked_columns: [],
  sample_rows: [[6214]],
  truncated: false,
  created_at: "2026-08-15T09:00:10Z",
};

/** Comfortably longer than the screen's 1500ms poll, so a stray tick would land. */
const POLL_QUIET_MS = 2200;

/** A response that arrives on a later task, the way a real one does. */
function delayed(body: unknown, ms = 5): Promise<Response> {
  return new Promise((resolve) => setTimeout(() => resolve(json(body)), ms));
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Routes on the URL rather than on call order. */
function routeFetch(overrides: Partial<Record<string, unknown>> = {}) {
  const calls: { url: string; init: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      if (url.includes("/executions/")) return Promise.resolve(json(overrides.execution ?? EXECUTION));
      if (url.includes("/events")) {
        return Promise.resolve(json({ run_id: "r1", events: [], last_seq: 0 }));
      }
      if (url.includes("/runs/")) return Promise.resolve(json(overrides.run ?? ANSWERED));
      // The thread's runs (B-106). Defaults to the same run the messages name.
      if (url.endsWith("/runs")) {
        if ("runs" in overrides) return Promise.resolve(json(overrides.runs));
        return Promise.resolve(json([overrides.run ?? ANSWERED]));
      }
      if (url.includes("/messages")) {
        if (init.method === "POST") {
          return Promise.resolve(
            json({ run_id: "r1", message_id: "m1", status: "queued", created: true }),
          );
        }
        return Promise.resolve(json(overrides.messages ?? MESSAGES));
      }
      return Promise.resolve(json(overrides.conversation ?? CONVERSATION));
    }),
  );
  return calls;
}

describe("<ConversationThread />", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  });

  it("shows the question, the answer and which database answered it", async () => {
    routeFetch();

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("6,214 orders were placed in July 2026.")).toBeInTheDocument();
    expect(screen.getByText("Pizza (PostgreSQL)")).toBeInTheDocument();
    expect(screen.getAllByText(/How many orders were placed in July 2026\?/).length).toBeGreaterThan(
      0,
    );
  });

  it("shows the query behind a lone citation without a second click", async () => {
    /** The product's central claim, made checkable rather than asserted. */
    routeFetch();

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(
      await screen.findByRole("button", { name: /Hide the query behind this/ }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/SELECT count\(\*\) AS "order_count"/)).toBeInTheDocument();
    expect(screen.getByText("6214")).toBeInTheDocument();
  });

  it("renders an honest refusal as a refusal, and not as a failure", async () => {
    routeFetch({
      run: { ...ANSWERED, findings: [], state: "refused" },
      messages: [
        MESSAGES[0],
        {
          id: "m2",
          role: "assistant",
          content:
            "This organization has more than one data source and this conversation is not tied to one of them: Pizza (PostgreSQL), Pizza (SQL Server).",
          run_id: "r1",
          created_at: "2026-08-15T09:00:05Z",
        },
      ],
    });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    // A run that could not answer completes (WP7.2b).
    expect(await screen.findByText(/more than one data source/)).toBeInTheDocument();
    expect(screen.getByText("could not answer")).toBeInTheDocument();
    expect(screen.queryByText("answered")).not.toBeInTheDocument();
    expect(screen.getByText("no supporting query")).toBeInTheDocument();
  });

  it("still says answered when the run answered", async () => {
    // The control.
    routeFetch({ run: { ...ANSWERED, state: "answered" } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("answered")).toBeInTheDocument();
    expect(screen.queryByText("could not answer")).not.toBeInTheDocument();
  });

  it("names the missing half when a run answered only part of the question", async () => {
    // The last hop of B-134's chain.
    routeFetch({ run: { ...ANSWERED, state: "partly", unanswered: "the cost" } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("could not answer the cost")).toBeInTheDocument();
    expect(screen.queryByText("answered")).not.toBeInTheDocument();
  });

  it("keeps the status word for a run that never recorded whether it answered", async () => {
    // Every run that ended before revision 0029 is this one.
    routeFetch({ run: { ...ANSWERED, findings: [], state: null } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("answered")).toBeInTheDocument();
  });

  it("says the platform failed when the platform failed", async () => {
    routeFetch({
      run: {
        ...ANSWERED,
        status: "failed",
        findings: [],
        failure_reason: "The run could not be completed.",
      },
    });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    // `failed` is reserved for the platform breaking.
    expect(await screen.findByText("failed")).toBeInTheDocument();
    expect(screen.getByText(/The run could not be completed/)).toBeInTheDocument();
  });

  it("shows what a live run is doing instead of a bare spinner", async () => {
    routeFetch({ run: { ...ANSWERED, status: "running", answer: null, findings: [] } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("working")).toBeInTheDocument();
    expect(screen.getByText(/The answer arrives here on its own/)).toBeInTheDocument();
  });

  it("sends a question with an idempotency key, so a double tap cannot bill twice", async () => {
    const calls = routeFetch();

    render(<ConversationThread orgId="o1" conversationId="c1" />);
    await screen.findByText("6,214 orders were placed in July 2026.");

    fireEvent.change(screen.getByLabelText("Ask a question"), {
      target: { value: "Which store sold most?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(calls.some((call) => call.init.method === "POST")).toBe(true));
    const post = calls.find((call) => call.init.method === "POST");
    const body = JSON.parse(String(post?.init.body)) as Record<string, string>;
    expect(body.content).toBe("Which store sold most?");
    // Required by the API, and the reason a retried send returns the run that already exists...
    expect(body.idempotency_key).toBeTruthy();
  });

  it("shows the answer as soon as the run finishes, with no further interaction", async () => {
    /** The bug the Phase 7 gate found, and the reason it did not pass. */
    let runCalls = 0;
    let answered = false;
    const calls: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        calls.push({ url, init });
        if (url.includes("/events")) return delayed({ run_id: "r1", events: [], last_seq: 0 });
        if (url.includes("/runs/")) {
          runCalls += 1;
          // Running first, finished afterwards — the transition is the thing.
          if (runCalls === 1) {
            return delayed({ ...ANSWERED, status: "running", answer: null, findings: [] });
          }
          answered = true;
          return delayed(ANSWERED);
        }
        if (url.includes("/messages")) {
          if (init.method === "POST") {
            return delayed({ run_id: "r1", message_id: "m1", status: "queued", created: true });
          }
          // The reply is written by the run, so it does not exist until the run has finished.
          return delayed(answered ? MESSAGES : [MESSAGES[0]]);
        }
        return delayed({ ...CONVERSATION, last_run_id: null, message_count: 0 });
      }),
    );

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    fireEvent.change(await screen.findByLabelText("Ask a question"), {
      target: { value: "How many orders were placed in July 2026?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    // No second question, no click, no refresh: the answer must simply appear.
    expect(
      await screen.findByText("6,214 orders were placed in July 2026.", undefined, {
        timeout: 4000,
      }),
    ).toBeInTheDocument();
  });

  it("is never a wordless answer, even if the thread has not caught up", async () => {
    /** Belt to the fix above's braces. */
    routeFetch({ messages: [] });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("6,214 orders were placed in July 2026.")).toBeInTheDocument();
  });

  it("does not print the answer twice once the reply is in the thread", async () => {
    /** The other half: with the reply present, the card must not restate it. */
    routeFetch();

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(
      await screen.findAllByText("6,214 orders were placed in July 2026."),
    ).toHaveLength(1);
  });

  it("stops polling once the run has finished", async () => {
    /** A page left open must not ask forever — and the fix moved the guard that stops it. */
    const calls = routeFetch();

    render(<ConversationThread orgId="o1" conversationId="c1" />);
    await screen.findByText("6,214 orders were placed in July 2026.");

    // Let the opening fetches land before counting.
    await new Promise((resolve) => setTimeout(resolve, POLL_QUIET_MS));
    const settled = calls.filter((call) => call.url.includes("/runs/")).length;
    await new Promise((resolve) => setTimeout(resolve, POLL_QUIET_MS));

    expect(calls.filter((call) => call.url.includes("/runs/")).length).toBe(settled);
  });

  it("will not send an empty question", async () => {
    routeFetch();

    render(<ConversationThread orgId="o1" conversationId="c1" />);
    await screen.findByText("6,214 orders were placed in July 2026.");

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });
});

describe("what the answer does not establish", () => {
  it("shows the limitations beside the answer", async () => {
    routeFetch({
      run: {
        ...ANSWERED,
        limitations: [
          "The investigation stopped before it was finished: I reached the maximum number of research steps for one question.",
          "9,999.00 appears in no result this run returned.",
        ],
      },
    });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/2 things to know/i)).toBeInTheDocument();
    expect(screen.getByText(/maximum number of research steps/i)).toBeInTheDocument();
    expect(screen.getByText(/appears in no result/i)).toBeInTheDocument();
  });

  it("says nothing at all when there is nothing to say", async () => {
    // A clean run should not be made to sound uncertain.
    routeFetch({ run: { ...ANSWERED, limitations: [] } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    await screen.findByText(/answered/i);
    expect(screen.queryByText(/things to know/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/one thing to know/i)).not.toBeInTheDocument();
  });

  it("counts one limitation in the singular", async () => {
    routeFetch({ run: { ...ANSWERED, limitations: ["Only one query returned rows."] } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/one thing to know/i)).toBeInTheDocument();
  });
});

describe("how the answer was reached", () => {
  // B-100. Architecture 4.2's fourth part of an answer.
  it("shows the method line with the answer", async () => {
    routeFetch({ run: { ...ANSWERED, method: "2 queries over 2 steps, against orders." } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/2 queries over 2 steps, against orders/i)).toBeInTheDocument();
  });

  it("says nothing when the run recorded no method", async () => {
    // A run answered before the column existed, or one that never composed.
    routeFetch({ run: { ...ANSWERED, method: "" } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    await screen.findByText(/answered/i);
    expect(screen.queryByText(/^How:/)).not.toBeInTheDocument();
  });
});

// jsdom draws nothing, so ECharts itself is stood in for.
const echartsInit = vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() }));
vi.mock("@/lib/echarts", () => ({ echarts: { init: echartsInit } }));

describe("the chart, and the reason there is none", () => {
  const SPEC = {
    $schema: "https://vega.github.io/schema/vega-lite/v5.json",
    mark: "bar",
    encoding: {
      x: { field: "month", type: "temporal" },
      y: { field: "revenue", type: "quantitative" },
    },
    data: { values: [{ month: "2026-07-01", revenue: 6214 }] },
  };

  it("draws the chart inside the answer, from the spec the server sent", async () => {
    /** B-048 and B-109. The chart is part of the claim, so it sits inside the answer card. */
    echartsInit.mockClear();
    routeFetch({ run: { ...ANSWERED, limitations: [], chart: { spec: SPEC } } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);
    const chart = await screen.findByTestId("chart");

    expect(chart.closest("[data-testid='answer']")).not.toBeNull();
    await waitFor(() => expect(echartsInit).toHaveBeenCalled());
  });
  it("says why there is no chart, where the chart would have been", async () => {
    // The case the whole design turned on.
    routeFetch({
      run: {
        ...ANSWERED,
        limitations: [],
        chart: {
          declined:
            "No chart was drawn: 'ingredient' has 4,812 distinct values and a chart here shows at most 50. The table has all of them.",
          code: "too_many_categories",
        },
      },
    });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/4,812 distinct values/)).toBeInTheDocument();
    // And it did not become a limitation: that region is about the truth of the answer.
    expect(screen.queryByText(/things to know/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/one thing to know/i)).not.toBeInTheDocument();
  });

  it("offers the spec, the way the SQL is offered", async () => {
    // B-048.
    routeFetch({ run: { ...ANSWERED, limitations: [], chart: { spec: SPEC } } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Chart spec" }));

    expect(await screen.findByText(/"mark": "bar"/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hide chart spec" })).toBeInTheDocument();
  });

  it("shows nothing at all when no chart was asked for", async () => {
    // Most answers. No empty frame and no placeholder.
    routeFetch({ run: { ...ANSWERED, limitations: [], chart: null } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    await screen.findByText(/answered/i);
    expect(screen.queryByRole("button", { name: "Chart spec" })).not.toBeInTheDocument();
    expect(screen.queryByText(/No chart was drawn/)).not.toBeInTheDocument();
  });

  it("renders a run recorded before charts existed", async () => {
    // `chart` is absent rather than null on an older run.
    routeFetch({ run: { ...ANSWERED, limitations: [] } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/6,214 orders/)).toBeInTheDocument();
  });
});

describe("which findings are evidence", () => {
  it("shows only the findings the answer rests on", async () => {
    routeFetch({
      run: {
        ...ANSWERED,
        answer: "Revenue fell because of delivery at one store.",
        findings: [
          { id: "f1", statement: "Revenue fell 12%.", support: ["x1"], confidence: "high", cited: true },
          { id: "f2", statement: "A step along the way.", support: ["x2"], confidence: "low", cited: false },
        ],
      },
    });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("Revenue fell 12%.")).toBeInTheDocument();
    // The uncited one is the investigation's working and lives in the trace.
    expect(screen.queryByText("A step along the way.")).not.toBeInTheDocument();
  });

  it("falls back to showing every finding when none is marked", async () => {
    // Runs written before WP9.2 have no `cited` on any finding.
    routeFetch({
      run: {
        ...ANSWERED,
        answer: "Two things happened.",
        findings: [
          { id: "f1", statement: "The first thing.", support: ["x1"], confidence: "high" },
          { id: "f2", statement: "The second thing.", support: ["x1"], confidence: "high" },
        ],
      },
    });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("The first thing.")).toBeInTheDocument();
    expect(screen.getByText("The second thing.")).toBeInTheDocument();
  });

  it("says which definitions governed the answer (B-087)", async () => {
    routeFetch({
      run: { ...ANSWERED, definitions_applied: ["prep_quantity"], definitions_available: 18 },
    });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/governed by prep_quantity/)).toBeInTheDocument();
  });

  it("says when a question matched none of the definitions that exist (B-087)", async () => {
    // The sentence three gate walks needed and never got.
    routeFetch({ run: { ...ANSWERED, definitions_applied: [], definitions_available: 18 } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/no definition matched this question/)).toBeInTheDocument();
    expect(screen.getByText(/18 defined here/)).toBeInTheDocument();
  });

  it("stays silent when there was nothing to match (B-087)", async () => {
    // The case that keeps the line worth reading.
    routeFetch({ run: { ...ANSWERED, definitions_applied: [], definitions_available: 0 } });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    await screen.findByText(/6,214 orders/);
    expect(screen.queryByText(/no definition matched/)).not.toBeInTheDocument();
    expect(screen.queryByText(/governed by/)).not.toBeInTheDocument();
  });

  it("renders a run recorded before these fields existed (B-087)", async () => {
    // Old rows carry neither field.
    routeFetch({ run: ANSWERED });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/6,214 orders/)).toBeInTheDocument();
    expect(screen.queryByText(/no definition matched/)).not.toBeInTheDocument();
  });
});


// --- An answer keeps its evidence when the next question is asked (B-106) ---

/** The chart the first answer carries. */
const FIRST_CHART = {
  $schema: "https://vega.github.io/schema/vega-lite/v5.json",
  mark: "bar",
  encoding: {
    x: { field: "month", type: "temporal", timeUnit: "yearmonth" },
    y: { field: "revenue", type: "quantitative" },
  },
  data: { values: [{ month: "2026-07-01", revenue: 6214 }] },
};

/** A second turn in the same thread, so there is an older answer to lose. */
const TWO_TURNS = [
  MESSAGES[0],
  MESSAGES[1],
  {
    id: "m3",
    role: "user",
    content: "and in August?",
    run_id: "r2",
    created_at: "2026-08-15T09:01:00Z",
  },
  {
    id: "m4",
    role: "assistant",
    content: "5,004 orders were placed in August 2026.",
    run_id: "r2",
    created_at: "2026-08-15T09:01:20Z",
  },
];

/** After a second question, the conversation's last run is the second one. */
const AFTER_TWO = { ...CONVERSATION, last_run_id: "r2", message_count: 4 };

const SECOND_RUN = {
  ...ANSWERED,
  id: "r2",
  question: "and in August?",
  answer: "5,004 orders were placed in August 2026.",
  findings: [
    { id: "f2", statement: "5,004 orders were placed in August 2026.", support: ["x1"], confidence: "high" },
  ],
};

describe("an answer keeps its evidence when the next question is asked (B-106)", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  });

  it("draws the first answer's chart after a second question has been answered", async () => {
    /** The gate walk's defect. The screen held one run and rendered one card. */
    routeFetch({
      conversation: AFTER_TWO,
      run: SECOND_RUN,
      messages: TWO_TURNS,
      runs: [{ ...ANSWERED, chart: { spec: FIRST_CHART } }, SECOND_RUN],
    });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    // Both answers are on the screen...
    expect(await screen.findByText("6,214 orders were placed in July 2026.")).toBeInTheDocument();
    expect(screen.getByText("5,004 orders were placed in August 2026.")).toBeInTheDocument();
    // ...and the older one still has its picture.
    expect(await screen.findByTestId("chart")).toBeInTheDocument();
  });

  it("keeps the evidence control on every answer, not just the newest", async () => {
    routeFetch({ conversation: AFTER_TWO, run: SECOND_RUN, messages: TWO_TURNS, runs: [ANSWERED, SECOND_RUN] });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    // One per answer. Anchored on the count rather than on presence.
    expect(
      await screen.findAllByRole("button", { name: /the query behind this/ }),
    ).toHaveLength(2);
  });

  it("asks for the thread's runs once, not once per answer", async () => {
    /** A screen whose cost grows with how much somebody has used it is one that gets slower... */
    const calls = routeFetch({ conversation: AFTER_TWO, run: SECOND_RUN, messages: TWO_TURNS, runs: [ANSWERED, SECOND_RUN] });

    render(<ConversationThread orgId="o1" conversationId="c1" />);
    expect(await screen.findByText("5,004 orders were placed in August 2026.")).toBeInTheDocument();

    expect(calls.filter((call) => call.url.endsWith("/runs")).length).toBe(1);
  });

  it("keeps the whole thread when the runs request fails outright", async () => {
    /** What CI caught and the unit tests did not. */
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init: RequestInit = {}) => {
        if (url.endsWith("/runs")) return Promise.resolve(json({ nope: true }, 500));
        if (url.includes("/executions/")) return Promise.resolve(json(EXECUTION));
        if (url.includes("/events")) {
          return Promise.resolve(json({ run_id: "r1", events: [], last_seq: 0 }));
        }
        if (url.includes("/runs/")) return Promise.resolve(json(ANSWERED));
        if (url.includes("/messages")) {
          if (init.method === "POST") {
            return Promise.resolve(
              json({ run_id: "r1", message_id: "m1", status: "queued", created: true }),
            );
          }
          return Promise.resolve(json(TWO_TURNS));
        }
        return Promise.resolve(json(AFTER_TWO));
      }),
    );

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("6,214 orders were placed in July 2026.")).toBeInTheDocument();
    expect(screen.getByText("5,004 orders were placed in August 2026.")).toBeInTheDocument();
    expect(screen.getAllByText("How many orders were placed in July 2026?").length).toBeGreaterThan(0);
  });

  it("falls back to the words when a run could not be fetched", async () => {
    /** The answer is what the reader came for. */
    routeFetch({ conversation: AFTER_TWO, run: SECOND_RUN, messages: TWO_TURNS, runs: [SECOND_RUN] });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("6,214 orders were placed in July 2026.")).toBeInTheDocument();
  });

  it("shows an answer once, not once in a bubble and once in a card", async () => {
    /** The Phase 7 rule, and the reason `replied` used to exist. */
    routeFetch({ conversation: AFTER_TWO, run: SECOND_RUN, messages: TWO_TURNS, runs: [ANSWERED, SECOND_RUN] });

    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText("6,214 orders were placed in July 2026.")).toBeInTheDocument();
    expect(screen.getAllByText("6,214 orders were placed in July 2026.")).toHaveLength(1);
  });
});

/** What the question cost (B-153). */
describe("how a table cell is aligned", () => {
  it("right-aligns numbers and money, and nothing else", () => {
    // B-179. The first version right-aligned every column but the first.
    for (const numeric of ["310817.09", "RM 310,817", "1,973 kg".replace(" kg", ""), "42", "-12.75", "87%", "RM 20,469.38"]) {
      expect(isNumeric(numeric)).toBe(true);
    }
  });

  it("leaves anything it cannot be sure about on the left", () => {
    // A wrongly right-aligned word is the fault this replaces, so doubt goes left.
    for (const words of [
      "Ayam Penyet+Nasi+Sup",
      "2025-12",
      "Annual undated view",
      "This is the gap between Outlet A and Outlet D",
      "",
      "  ",
      "1,973 kg",
    ]) {
      expect(isNumeric(words)).toBe(false);
    }
  });

  it("reads a number out of nested markup", () => {
    // Money is bolded by the answer rule.
    expect(isNumeric(["RM 310,817"])).toBe(true);
  });
});

describe("how far through its allowance a run is", () => {
  const withProgress = (used: object, limits: object) =>
    ({ ...ANSWERED, progress: { used, limits } }) as unknown as Parameters<typeof progressLine>[0];

  it("counts steps and time, and predicts nothing", () => {
    // B-177. A bar claims to know when a run finishes.
    const run = withProgress(
      { iterations: 6, wall_seconds: 210 },
      { iterations: 12, wall_seconds: 330 },
    );

    expect(progressLine(run)).toBe("step 6 of 12 · 3:30 of 5:30");
  });

  it("says nothing at all before the run has done anything", () => {
    // "step 0 of 12" while the catalog is still being searched measures the wrong thing.
    expect(progressLine(ANSWERED as unknown as Parameters<typeof progressLine>[0])).toBeNull();
  });

  it("warns when a ceiling is close, before the answer arrives", () => {
    // Saying it early is the feature.
    const close = withProgress(
      { iterations: 11, wall_seconds: 200 },
      { iterations: 12, wall_seconds: 330 },
    );
    const early = withProgress(
      { iterations: 2, wall_seconds: 40 },
      { iterations: 12, wall_seconds: 330 },
    );

    expect(nearlyOut(close)).toBe(true);
    expect(nearlyOut(early)).toBe(false);
  });

  it("is not confused by a run that reports one dimension and not the other", () => {
    const partial = withProgress({ iterations: 3 }, { iterations: 12 });

    expect(progressLine(partial)).toBe("step 3 of 12");
    expect(nearlyOut(partial)).toBe(false);
  });
});

describe("how an answer is rendered", () => {
  it("highlights whole directional phrases even when Markdown splits the bold number", async () => {
    const words = "Sales are up **6.2%** at **$1.42M**. **Outlet A**, down **18.2%**, needs a look. Use `down 9%` as code.";
    routeFetch({run: {...ANSWERED, answer: words}, messages: [MESSAGES[0], {...MESSAGES[1], content: words}]});
    render(<ConversationThread orgId="o1" conversationId="c1" />);
    const answer = await screen.findByTestId("answer-text");
    expect(answer.querySelector("mark.up")?.textContent).toBe("up 6.2%");
    expect(answer.querySelector("mark.down")?.textContent).toBe("Outlet A, down 18.2%");
    expect(answer.querySelector("strong")?.textContent).toBe("$1.42M");
    expect(answer.querySelector("code")?.textContent).toBe("down 9%");
    expect(answer.querySelector("code mark")).toBeNull();
  });

  it("renders both comparison lines from the returned message, with a legend and the original table", async () => {
    echartsInit.mockClear();
    const markdown = [
      "| Month | Outlet A orders | Outlet A sales | Outlet B orders | Outlet B sales | Ahead |",
      "| --- | --- | --- | --- | --- | --- |",
      "| Jan 2025 | 10 | **1,000** | 20 | **900** | A |",
      "| Feb 2025 | 12 | **1,200** | 22 | **1,300** | B |",
      "| Mar 2025 | 14 | **1,400** | 24 | **1,100** | A |",
    ].join("\n");
    routeFetch({ run: { ...ANSWERED, answer: markdown, chart: null },
      messages: [MESSAGES[0], { ...MESSAGES[1], content: markdown }] });
    render(<ConversationThread orgId="o1" conversationId="c1" />);
    await screen.findByTestId("table-chart");
    await waitFor(() => expect(echartsInit.mock.results[0]?.value.setOption).toHaveBeenCalled());
    const option = echartsInit.mock.results[0]!.value.setOption.mock.calls[0]![0] as unknown as {
      legend: unknown;
      series: { name: string; type: string; data: number[]; lineStyle: { color: string } }[];
    };
    expect(option.legend).toBeDefined();
    expect(option.series.map(({ name, type, data }) => ({ name, type, data }))).toEqual([
      { name: "Outlet A sales", type: "line", data: [1000, 1200, 1400] },
      { name: "Outlet B sales", type: "line", data: [900, 1300, 1100] },
    ]);
    expect(new Set(option.series.map((series) => series.lineStyle.color)).size).toBe(2);
    fireEvent.click(screen.getByRole("button", { name: /^Table$/ }));
    expect(screen.getByRole("cell", { name: "1,000" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "900" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Outlet A orders" })).toBeInTheDocument();
  });

  it("renders a business review from the returned message as four cards and interleaved charts", async () => {
    const markdown = [
      "Sales grew, with one outlet needing attention.",
      "",
      "| Metric | Value | Change | Comparison |",
      "| --- | --- | --- | --- |",
      "| Net sales | RM 12,000 | +20.0% | vs prior month |",
      "| Orders | 600 | +10.0% | vs prior month |",
      "| Average order | RM 20.00 | +9.1% | vs prior month |",
      "| Outlets up | 2 of 3 | 1 fell | comparable outlets |",
      "",
      "## Outlet performance",
      "Outlet C declined while the others grew.",
      "",
      "| Outlet | Sales change (%) |",
      "| --- | --- |",
      "| Outlet A | +30.0% |",
      "| Outlet B | +20.0% |",
      "| Outlet C | -10.0% |",
      "",
      "## Daily sales",
      "The final day shown was the strongest.",
      "",
      "| Date | Net sales |",
      "| --- | --- |",
      "| 2025-12-01 | RM 300 |",
      "| 2025-12-02 | RM 350 |",
      "| 2025-12-03 | RM 400 |",
      "",
      "Check Outlet C before assigning a cause.",
    ].join("\n");
    routeFetch({
      run: { ...ANSWERED, answer: markdown, chart: null },
      messages: [MESSAGES[0], { ...MESSAGES[1], content: markdown }],
    });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    const answer = await screen.findByTestId("answer-text");
    const cardLabels = ["Net sales", "Orders", "Average order", "Outlets up"];
    for (const label of cardLabels) {
      expect(screen.getByText(label, { exact: true }).closest("table")).toBeNull();
    }
    expect(screen.getAllByText("vs prior month")).toHaveLength(3);
    expect(screen.getByText("comparable outlets")).toBeInTheDocument();
    await waitFor(() => expect(answer.querySelectorAll('[data-testid="table-chart"]')).toHaveLength(2));
    const figures = [...answer.querySelectorAll("figure")];
    expect(figures[0]?.textContent).toContain("Sales change (%) by outlet");
    expect(figures[1]?.textContent).toContain("Net sales by date");
    expect(answer.textContent?.indexOf("Outlet performance")).toBeLessThan(answer.textContent?.indexOf("Daily sales") ?? 0);

    fireEvent.click(screen.getAllByRole("button", { name: /^Table$/ })[0]!);
    expect(screen.getByRole("cell", { name: "Outlet C" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "-10.0%" })).toBeInTheDocument();
    expect(answer.querySelectorAll('[data-testid="table-chart"]')).toHaveLength(1);
  });

  it("shows headings, lists and tables as structure rather than as characters", async () => {
    // B-172. This rendered into a bare `<p>` with `white-space: pre-wrap`.
    const markdown = [
      "## Products with high sales",
      "",
      "* **Sup Buntut** - RM737.68",
      "* **Peha** - RM368.97",
      "",
      "| Product | Waste RM |",
      "| --- | --- |",
      "| Peha | 64.59 |",
    ].join("\n");
    // The card renders the message where one exists.
    routeFetch({
      run: { ...ANSWERED, answer: markdown },
      messages: [MESSAGES[0], { ...MESSAGES[1], content: markdown }],
    });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    const answer = await screen.findByTestId("answer-text");
    expect(answer.querySelector("h2")?.textContent).toBe("Products with high sales");
    expect(answer.querySelectorAll("li")).toHaveLength(2);
    expect(answer.querySelector("strong")?.textContent).toBe("Sup Buntut");
    // The table needs remark-gfm; without it this is four lines of pipes.
    expect(answer.querySelector("table")).not.toBeNull();
    expect(answer.querySelector("th")?.textContent).toBe("Product");
    // And the markup must not leak through as text.
    expect(answer.textContent).not.toContain("##");
    expect(answer.textContent).not.toContain("| --- |");
  });

  it("escapes HTML in an answer rather than rendering it", async () => {
    // The answer is written by a model that has just read customer rows.
    const hostile = 'Sales rose. <img src=x onerror="alert(1)"> <script>alert(2)</script> Done.';
    routeFetch({
      run: { ...ANSWERED, answer: hostile },
      messages: [MESSAGES[0], { ...MESSAGES[1], content: hostile }],
    });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    const answer = await screen.findByTestId("answer-text");
    expect(answer.querySelector("img")).toBeNull();
    expect(answer.querySelector("script")).toBeNull();
    expect(answer.textContent).toContain("Sales rose.");
  });

  it("still renders an answer that carries no markdown at all", async () => {
    // Most answers are a sentence.
    routeFetch({ run: ANSWERED });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByText(/6,214 orders were placed in July 2026/)).toBeInTheDocument();
  });
});

describe("what the run cost", () => {
  const priced = { ...ANSWERED, cost_estimate: "0.0195", model_usage: { calls: 3, input_tokens: 1700, output_tokens: 170, unpriced_calls: 0, by_model: [] } };

  it("shows the total and where it went", async () => {
    routeFetch({ run: priced });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    const cost = await screen.findByTestId("run-cost");
    // Two decimals at or above a cent, four below it: $0.0195 reads as $0.02.
    expect(cost).toHaveTextContent("$0.02");
    expect(cost).toHaveTextContent("3 model calls");
    expect(cost).toHaveTextContent("1,870 tokens");
  });

  it("says 'not priced' rather than a number that understates", async () => {
    // The rule both columns were born with: null means unpriced, never free.
    routeFetch({
      run: {
        ...ANSWERED,
        cost_estimate: null,
        model_usage: { calls: 5, input_tokens: 10, output_tokens: 2, unpriced_calls: 1, by_model: [] },
      },
    });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    const cost = await screen.findByTestId("run-cost");
    expect(cost).toHaveTextContent("not priced");
    // The absence stays informative: it says how many calls could not be priced rather than...
    expect(cost).toHaveTextContent("1 not priced");
    expect(cost.textContent).not.toMatch(/\$/);
  });

  it("never renders a sub-cent run as free", async () => {
    // `agent_runs.cost_estimate` stores four decimal places while the ledger prices each call...
    routeFetch({
      run: {
        ...ANSWERED,
        cost_estimate: "0.0000",
        model_usage: { calls: 1, input_tokens: 8, output_tokens: 1, unpriced_calls: 0, by_model: [] },
      },
    });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    const cost = await screen.findByTestId("run-cost");
    expect(cost).toHaveTextContent("less than $0.0001");
    expect(cost.textContent).not.toContain("$0.0000");
  });

  it("says how much of the input was cached, because the total does not discount it", async () => {
    // Revision 0034.
    routeFetch({
      run: {
        ...priced,
        model_usage: { ...priced.model_usage, cached_input_tokens: 1200 },
      },
    });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByTestId("run-cost")).toHaveTextContent("1,200 cached");
  });

  it("says when the token counts are our arithmetic rather than the provider's", async () => {
    // Estimated tokens are priced as if measured.
    routeFetch({
      run: { ...priced, model_usage: { ...priced.model_usage, estimated_calls: 2 } },
    });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    expect(await screen.findByTestId("run-cost")).toHaveTextContent("2 estimated");
  });

  it("renders nothing when the organization has spend switched off (D-066)", async () => {
    // The API withholds `cost_estimate` and `model_usage` rather than the screen declining to...
    routeFetch({ run: { ...ANSWERED, cost_estimate: null, model_usage: {} } });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    await screen.findByText(/6,214 orders/);
    expect(screen.queryByTestId("run-cost")).toBeNull();
  });

  it("shows nothing at all for a run that recorded no usage", async () => {
    // Older runs, and runs that ended before a model was called.
    routeFetch({ run: { ...ANSWERED, cost_estimate: null, model_usage: {} } });
    render(<ConversationThread orgId="o1" conversationId="c1" />);

    await screen.findByText(/6,214 orders/);
    expect(screen.queryByTestId("run-cost")).toBeNull();
  });
});
