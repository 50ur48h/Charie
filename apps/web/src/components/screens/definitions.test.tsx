import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  acceptanceSummary,
  badgeLabel,
  badgeTone,
  changesFrom,
  describeFilter,
  describeProvenance,
  describeVersion,
  Definitions,
  editSummary,
} from "./definitions";

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

const PROPOSAL = {
  id: "p1",
  name: "anchor_order",
  description: "A completed order over 40 pounds placed on a weekday.",
  expression: "count(orders.id)",
  caveat: "Weekday only, so weekend demand is not represented.",
  synonyms: ["anchor orders"],
  provenance: { kind: "import", table: "public.meta_metric", snapshot_id: "s1" },
};

const BINDING = {
  id: "d1",
  name: "net_revenue",
  kind: "metric",
  description: "Revenue excluding cancelled and refunded orders.",
  expression: "sum(orders.total_amount)",
  caveat: null,
  required_filters: [
    { table: "orders", column: "status", op: "not_in", values: ["cancelled", "refunded"] },
  ],
  synonyms: ["net sales"],
  binds: true,
  version: 2,
};

const PROSE = {
  ...BINDING,
  id: "d2",
  name: "basket_size",
  description: "What an average order is worth.",
  required_filters: [],
  synonyms: [],
  binds: false,
  version: 1,
};

function json(body: unknown, status = 200): Response {
  if (status === 204) return new Response(null, { status });
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** The screen loads definitions and proposals together. */
function stubFetch(
  routes: {
    definitions?: Response;
    proposals?: Response;
    retired?: Response;
    versions?: Response;
    patch?: Response;
    post?: Response;
  } = {},
) {
  const calls: { url: string; init: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      if (url.endsWith("/definitions/proposals")) {
        return Promise.resolve((routes.proposals ?? json([])).clone());
      }
      // Before the bare `/definitions` check.
      if (url.endsWith("/definitions?status=retired")) {
        return Promise.resolve((routes.retired ?? json([])).clone());
      }
      if (url.endsWith("/versions")) {
        return Promise.resolve((routes.versions ?? json([])).clone());
      }
      // Method before URL: writing one by hand.
      if (init.method === "POST" && url.endsWith("/definitions")) {
        return Promise.resolve(
          (routes.post ?? json({ ...BINDING, id: "new", name: "net_revenue" })).clone(),
        );
      }
      if (url.endsWith("/definitions")) {
        return Promise.resolve((routes.definitions ?? json([])).clone());
      }
      if (init.method === "PATCH") {
        return Promise.resolve((routes.patch ?? json({ ...BINDING, version: 3 })).clone());
      }
      if (init.method === "DELETE") {
        return Promise.resolve(json(null, 204));
      }
      return Promise.resolve(json({}, 200));
    }),
  );
  return calls;
}

/** The open editor, scoped. */
function inEditor() {
  const save = screen.getByRole("button", { name: "Save changes" });
  const item = save.closest("li");
  if (!item) throw new Error("The editor is not open.");
  return within(item);
}

/** The body of the last request made with this method. */
function bodyOf(calls: { url: string; init: RequestInit }[], method: string): unknown {
  const sent = calls.filter((call) => call.init.method === method).at(-1);
  return sent?.init.body ? JSON.parse(String(sent.init.body)) : undefined;
}

describe("describeFilter", () => {
  it("reads a filter the way the prompt words it", () => {
    // The same phrasing the API's `describe()` uses.
    expect(describeFilter(BINDING.required_filters[0]!)).toBe(
      "orders.status none of cancelled, refunded",
    );
  });
});

describe("describeProvenance", () => {
  it("names the table an import read", () => {
    expect(describeProvenance(PROPOSAL.provenance)).toBe("Imported from public.meta_metric");
  });

  it("says nothing when there is nothing to say", () => {
    // A definition typed by hand has no provenance.
    expect(describeProvenance({})).toBeNull();
  });
});

describe("acceptanceSummary", () => {
  it("warns that accepting with no filters binds nothing", () => {
    // D-033's disclosure, at the moment somebody can still change their mind.
    const summary = acceptanceSummary([]);

    expect(summary).toContain("binds nothing");
    expect(summary).toContain("an answer resting on it will say so");
  });

  it("says a query ignoring the filters will be blocked", () => {
    expect(acceptanceSummary(BINDING.required_filters)).toContain("blocked");
  });
});

describe("badgeLabel", () => {
  it("says enforced when the filters actually separate rows", () => {
    expect(badgeLabel(BINDING)).toBe("enforced");
    expect(badgeTone(BINDING)).toBe("mint");
  });

  it("says prose only when nothing is checked", () => {
    expect(badgeLabel(PROSE)).toBe("prose only");
    expect(badgeTone(PROSE)).toBe("neutral");
  });

  it("does not claim enforcement a hollow filter is not delivering (B-171)", () => {
    // `edible_waste` badged `enforced` over `edible_flag = 1` after MiseQ v6.7 made that column...
    const hollow = { ...BINDING, excluding_nothing: ["orders.status"] };

    expect(badgeLabel(hollow)).toBe("enforced, but currently excluding nothing");
    expect(badgeTone(hollow)).toBe("peach");
  });

  it("reads an absent field as fine rather than as hollow", () => {
    // An older API does not send it.
    const older = { ...BINDING };

    expect("excluding_nothing" in older).toBe(false);
    expect(badgeLabel(older)).toBe("enforced");
  });
});

describe("changesFrom", () => {
  it("sends only the field that moved", () => {
    // The omission is the contract (B-088).
    const changes = changesFrom(BINDING, {
      description: "Revenue excluding cancelled and refunded orders.",
      expression: "sum(orders.total_amount)",
      caveat: "",
      synonyms: "net sales",
      filters: BINDING.required_filters,
    });

    expect(changes).toEqual({});
  });

  it("clears a formula with null rather than an empty string", () => {
    // The one place where absent and null differ: a metric with no formula is a real thing to say.
    const changes = changesFrom(BINDING, {
      description: BINDING.description,
      expression: "   ",
      caveat: "",
      synonyms: "net sales",
      filters: BINDING.required_filters,
    });

    expect(changes).toEqual({ expression: null });
  });

  it("sends an empty filter list when the last filter is removed", () => {
    // "Stop enforcing this, keep the prose" is a real request.
    const changes = changesFrom(BINDING, {
      description: BINDING.description,
      expression: "sum(orders.total_amount)",
      caveat: "",
      synonyms: "net sales",
      filters: [],
    });

    expect(changes).toEqual({ required_filters: [] });
  });
});

describe("editSummary", () => {
  it("says when nothing has changed", () => {
    expect(
      editSummary(BINDING, {
        description: BINDING.description,
        expression: "sum(orders.total_amount)",
        caveat: "",
        synonyms: "net sales",
        filters: BINDING.required_filters,
      }),
    ).toContain("Nothing has changed");
  });

  it("says plainly when an edit stops enforcing anything", () => {
    // The same disclosure `acceptanceSummary` makes, at the other end of a definition's life.
    const summary = editSummary(BINDING, {
      description: BINDING.description,
      expression: "sum(orders.total_amount)",
      caveat: "",
      synonyms: "net sales",
      filters: [],
    });

    expect(summary).toContain("stops enforcing anything");
  });

  it("never reads as a receipt", () => {
    // The first draft opened every line with "Saved, …".
    const drafts = [
      { description: "Changed.", expression: "", caveat: "", synonyms: "", filters: [] },
      {
        description: BINDING.description,
        expression: "sum(orders.total_amount)",
        caveat: "",
        synonyms: "net sales",
        filters: BINDING.required_filters,
      },
      {
        description: BINDING.description,
        expression: "sum(orders.total_amount)",
        caveat: "",
        synonyms: "net sales",
        filters: [{ table: "orders", column: "status", op: "in", values: ["completed"] }],
      },
    ];

    for (const draft of drafts) {
      expect(editSummary(BINDING, draft)).not.toMatch(/^Saved\b/);
    }
  });

  it("leaves enforcement alone when only the prose changed", () => {
    const summary = editSummary(BINDING, {
      description: "Something else entirely.",
      expression: "sum(orders.total_amount)",
      caveat: "",
      synonyms: "net sales",
      filters: BINDING.required_filters,
    });

    expect(summary).toContain("leaves what is enforced alone");
  });
});

describe("describeVersion", () => {
  it("reads a version as what happened and what it enforced", () => {
    expect(
      describeVersion({
        version: 2,
        change: "updated",
        name: "net_revenue",
        description: "Revenue excluding cancelled and refunded orders.",
        expression: null,
        caveat: null,
        required_filters: BINDING.required_filters,
        synonyms: [],
        status: "active",
        changed_by: "u1",
        changed_at: "2026-08-18T10:00:00Z",
      }),
    ).toBe("v2 — edited, enforced orders.status none of cancelled, refunded");
  });

  it("reads a reinstatement as its own act, not as an edit", () => {
    // A history that called it an edit would read as though somebody had changed the wording.
    expect(
      describeVersion({
        version: 6,
        change: "reinstated",
        name: "waste_cost",
        description: "Cost of recorded waste.",
        expression: null,
        caveat: null,
        required_filters: [],
        synonyms: [],
        status: "active",
        changed_by: "u1",
        changed_at: "2026-08-19T10:00:00Z",
      }),
    ).toBe("v6 — brought back into force, enforced nothing");
  });

  it("says when a version enforced nothing", () => {
    expect(
      describeVersion({
        version: 1,
        change: "accepted",
        name: "basket_size",
        description: "What an average order is worth.",
        expression: null,
        caveat: null,
        required_filters: [],
        synonyms: [],
        status: "active",
        changed_by: null,
        changed_at: "2026-08-18T10:00:00Z",
      }),
    ).toBe("v1 — accepted from a proposal, enforced nothing");
  });
});

describe("<Definitions />", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  });

  it("shows a proposal, what it says, and where it came from", async () => {
    stubFetch({ proposals: json([PROPOSAL]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(await screen.findByText("anchor_order")).toBeInTheDocument();
    expect(screen.getByText(/completed order over 40 pounds/)).toBeInTheDocument();
    expect(screen.getByText("Imported from public.meta_metric")).toBeInTheDocument();
  });

  it("puts an imported caveat in front of the Admin who is about to bless it", async () => {
    // The reason `caveat` exists is that it reaches a reader.
    stubFetch({ proposals: json([PROPOSAL]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(await screen.findByText(/Weekday only, so weekend demand/)).toBeInTheDocument();
  });

  it("shows the caveat on a definition in force", async () => {
    stubFetch({
      definitions: json([{ ...BINDING, caveat: "Excludes samples, so it understates stock." }]),
    });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(await screen.findByText(/Excludes samples/)).toBeInTheDocument();
  });

  it("writes a definition by hand, through the form, with its filter", async () => {
    // B-169, and the point is the route.
    const calls = stubFetch({});

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText("Write one by hand");

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "net_revenue" } });
    fireEvent.change(screen.getByLabelText("Answers must say (optional)"), {
      target: { value: "Excludes refunds." },
    });
    fireEvent.change(screen.getByLabelText("Also called"), {
      target: { value: "net sales, takings" },
    });
    fireEvent.change(screen.getByLabelText("Filter table"), { target: { value: "orders" } });
    fireEvent.change(screen.getByLabelText("Filter column"), { target: { value: "status" } });
    fireEvent.change(screen.getByLabelText("Filter values"), { target: { value: "completed" } });
    fireEvent.click(screen.getByRole("button", { name: "Add this filter" }));

    // Description last, so the button's enabling is observed rather than assumed.
    const create = screen.getByRole("button", { name: "Create definition" });
    expect(create).toBeDisabled();
    fireEvent.change(screen.getByLabelText("What it means"), {
      target: { value: "Sales after discounts." },
    });
    fireEvent.click(create);

    await waitFor(() => expect(bodyOf(calls, "POST")).toBeDefined());
    expect(bodyOf(calls, "POST")).toEqual({
      name: "net_revenue",
      description: "Sales after discounts.",
      caveat: "Excludes refunds.",
      synonyms: ["net sales", "takings"],
      required_filters: [{ table: "orders", column: "status", op: "in", values: ["completed"] }],
    });
  });

  it("omits the fields nobody filled in rather than sending them empty", async () => {
    // `expression: ""` is a formula that is the empty string, and the API would store it as one.
    const calls = stubFetch({});

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText("Write one by hand");
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "basket_size" } });
    fireEvent.change(screen.getByLabelText("What it means"), {
      target: { value: "What an average order is worth." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create definition" }));

    await waitFor(() => expect(bodyOf(calls, "POST")).toBeDefined());
    expect(bodyOf(calls, "POST")).toEqual({
      name: "basket_size",
      description: "What an average order is worth.",
    });
  });

  it("says whether what was just written binds anything", async () => {
    // D-033 at the moment it happens.
    stubFetch({ post: json({ ...PROSE, name: "basket_size", binds: false }) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText("Write one by hand");
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "basket_size" } });
    fireEvent.change(screen.getByLabelText("What it means"), { target: { value: "Worth." } });
    fireEvent.click(screen.getByRole("button", { name: "Create definition" }));

    expect(await screen.findByText(/in force as prose/)).toBeInTheDocument();
  });

  it("offers no way to write one to a Reader (B-008)", async () => {
    stubFetch({});

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="reader" />);
    await screen.findByText(/Definitions/);

    expect(screen.queryByText("Write one by hand")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Create definition" })).not.toBeInTheDocument();
  });

  it("shows on the card which filter is excluding nothing (B-171)", async () => {
    // The badge says that something is hollow; this says which.
    stubFetch({
      definitions: json([{ ...BINDING, excluding_nothing: ["orders.status"] }]),
    });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(
      await screen.findByText("enforced, but currently excluding nothing"),
    ).toBeInTheDocument();
    // The explanation, not the filter list — both name the column.
    expect(screen.getByText(/holds a single value that this filter accepts/)).toBeInTheDocument();
  });

  it("separates what is enforced from what is only prose", async () => {
    // The whole of D-033 on one screen.
    stubFetch({ definitions: json([BINDING, PROSE]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(await screen.findByText("net_revenue")).toBeInTheDocument();
    expect(screen.getByText("enforced")).toBeInTheDocument();
    expect(screen.getByText("prose only")).toBeInTheDocument();
    expect(screen.getByText(/Nothing checks this one/)).toBeInTheDocument();
  });

  it("offers a Reader no control the API would refuse (B-008)", async () => {
    stubFetch({ definitions: json([BINDING]), proposals: json([PROPOSAL]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="reader" />);

    expect(await screen.findByText(/Only an Admin can review/)).toBeInTheDocument();
    expect(screen.queryByText("Import")).not.toBeInTheDocument();
    expect(screen.queryByText("Reject")).not.toBeInTheDocument();
    expect(screen.queryByText("anchor_order")).not.toBeInTheDocument();
  });

  it("fails closed while the role is still unknown", async () => {
    stubFetch({ proposals: json([PROPOSAL]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role={null} />);

    expect(await screen.findByText(/Only an Admin can review/)).toBeInTheDocument();
  });

  it("asks the API for nothing when the role would be refused", async () => {
    // A 403 for a screen that never offered the action is noise.
    const calls = stubFetch({ proposals: json([PROPOSAL]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="reader" />);
    await screen.findByText(/Only an Admin can review/);

    expect(calls.filter((call) => call.url.includes("/definitions"))).toHaveLength(0);
  });

  it("says accepting without filters will bind nothing, before the click", async () => {
    stubFetch({ proposals: json([PROPOSAL]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(await screen.findByText("anchor_order")).toBeInTheDocument();
    expect(screen.getByText(/binds nothing/)).toBeInTheDocument();
    expect(screen.getByText("Accept as prose")).toBeInTheDocument();
  });

  it("changes what the button promises once a filter is staged", async () => {
    // The button names the act it is about to perform.
    stubFetch({ proposals: json([PROPOSAL]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText("anchor_order");

    fireEvent.change(screen.getByLabelText("Table"), { target: { value: "orders" } });
    fireEvent.change(screen.getByLabelText("Column"), { target: { value: "status" } });
    fireEvent.change(screen.getByLabelText("Must be"), { target: { value: "eq" } });
    fireEvent.change(screen.getByLabelText("Values"), { target: { value: "completed" } });
    fireEvent.click(screen.getByText("Add filter"));

    expect(await screen.findByText("orders.status equal to completed")).toBeInTheDocument();
    expect(screen.getByText("Accept and enforce")).toBeInTheDocument();
    expect(screen.getByText(/is blocked before the answer is written/)).toBeInTheDocument();
  });

  it("sends the staged filters when it accepts", async () => {
    const calls = stubFetch({ proposals: json([PROPOSAL]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText("anchor_order");

    fireEvent.change(screen.getByLabelText("Table"), { target: { value: "orders" } });
    fireEvent.change(screen.getByLabelText("Column"), { target: { value: "status" } });
    fireEvent.change(screen.getByLabelText("Values"), { target: { value: "completed" } });
    fireEvent.click(screen.getByText("Add filter"));
    fireEvent.click(await screen.findByText("Accept and enforce"));

    await waitFor(() => {
      const accept = calls.find((call) => call.url.endsWith("/accept"));
      expect(accept).toBeDefined();
      expect(JSON.parse(String(accept?.init.body))).toEqual({
        required_filters: [
          { table: "orders", column: "status", op: "in", values: ["completed"] },
        ],
      });
    });
  });

  it("keeps a rejected filter on screen to correct rather than retype", async () => {
    // The API's message names the column that was wrong.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/definitions/proposals")) {
          return Promise.resolve(json([PROPOSAL]));
        }
        if (url.endsWith("/accept")) {
          return Promise.resolve(
            json({ detail: "'anchor_order' requires a filter on orders.stats, and 'orders' has no column called 'stats'." }, 400),
          );
        }
        return Promise.resolve(json([]));
      }),
    );

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText("anchor_order");

    fireEvent.change(screen.getByLabelText("Table"), { target: { value: "orders" } });
    fireEvent.change(screen.getByLabelText("Column"), { target: { value: "stats" } });
    fireEvent.change(screen.getByLabelText("Values"), { target: { value: "completed" } });
    fireEvent.click(screen.getByText("Add filter"));
    fireEvent.click(await screen.findByText("Accept and enforce"));

    expect(await screen.findByText(/no column called 'stats'/)).toBeInTheDocument();
    expect(screen.getByText("orders.stats one of completed")).toBeInTheDocument();
  });

  it("says an import that proposed nothing succeeded", async () => {
    // An empty list alone answers neither "done" nor "did my mapping fail".
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/definitions/import")) return Promise.resolve(json([], 201));
        return Promise.resolve(json([]));
      }),
    );

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText(/Nothing waiting/);

    fireEvent.change(screen.getByLabelText("Metric table"), {
      target: { value: "meta_metric" },
    });
    fireEvent.change(screen.getByLabelText("Name column"), { target: { value: "metric_key" } });
    fireEvent.change(screen.getByLabelText("Definition column"), {
      target: { value: "definition_text" },
    });
    fireEvent.click(screen.getByText("Import"));

    expect(await screen.findByText(/already known here/)).toBeInTheDocument();
  });

  it("carries the customer's own names into the import (B-085, B-087)", async () => {
    // The field the form did not have.
    const calls = stubFetch();

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText(/Nothing waiting/);

    fireEvent.change(screen.getByLabelText("Metric table"), {
      target: { value: "meta_metric" },
    });
    fireEvent.change(screen.getByLabelText("Name column"), { target: { value: "metric_key" } });
    fireEvent.change(screen.getByLabelText("Definition column"), {
      target: { value: "definition" },
    });
    fireEvent.change(screen.getByLabelText("Names column (optional)"), {
      target: { value: "metric_name" },
    });
    fireEvent.click(screen.getByText("Import"));

    await waitFor(() => {
      const call = calls.find((entry) => entry.url.endsWith("/definitions/import"));
      expect(call).toBeDefined();
      expect(JSON.parse(String(call?.init.body))).toMatchObject({
        table: "meta_metric",
        name_column: "metric_key",
        description_column: "definition",
        synonyms_column: "metric_name",
      });
    });
  });

  it("omits the optional columns rather than sending them empty", async () => {
    // An empty string is a column name the API would look for and never find.
    const calls = stubFetch();

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    await screen.findByText(/Nothing waiting/);

    fireEvent.change(screen.getByLabelText("Metric table"), { target: { value: "m" } });
    fireEvent.change(screen.getByLabelText("Name column"), { target: { value: "k" } });
    fireEvent.change(screen.getByLabelText("Definition column"), { target: { value: "d" } });
    fireEvent.click(screen.getByText("Import"));

    await waitFor(() => {
      const call = calls.find((entry) => entry.url.endsWith("/definitions/import"));
      const body = JSON.parse(String(call?.init.body)) as Record<string, unknown>;
      expect(body).not.toHaveProperty("synonyms_column");
      expect(body).not.toHaveProperty("expression_column");
    });
  });

  it("corrects a filter on a definition already in force", async () => {
    // B-088, and the whole of it.
    const calls = stubFetch({ definitions: json([BINDING]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(inEditor().getByLabelText("What it means"), {
      target: { value: "Revenue, excluding anything cancelled." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(bodyOf(calls, "PATCH")).toBeDefined());
    // Only the field that moved.
    expect(bodyOf(calls, "PATCH")).toEqual({
      description: "Revenue, excluding anything cancelled.",
    });
  });

  it("adds a filter to a definition that binds nothing", async () => {
    const calls = stubFetch({ definitions: json([PROSE]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Table"), { target: { value: "orders" } });
    fireEvent.change(screen.getByLabelText("Column"), { target: { value: "status" } });
    fireEvent.change(screen.getByLabelText("Values"), { target: { value: "completed" } });
    fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(bodyOf(calls, "PATCH")).toBeDefined());
    expect(bodyOf(calls, "PATCH")).toEqual({
      required_filters: [{ table: "orders", column: "status", op: "in", values: ["completed"] }],
    });
  });

  it("says what saving will do before it is saved", async () => {
    // The same disclosure accepting makes, at the other end of a definition's life.
    stubFetch({ definitions: json([BINDING]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove" }));

    expect(screen.getByText(/stops enforcing anything/)).toBeInTheDocument();
  });

  it("keeps a refused edit on screen to correct", async () => {
    // The API refuses a filter naming a column this database does not have.
    const calls = stubFetch({
      definitions: json([BINDING]),
      patch: json({ detail: "'net_revenue' requires a filter on orders.nope" }, 400),
    });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(inEditor().getByLabelText("What it means"), {
      target: { value: "Something else." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(bodyOf(calls, "PATCH")).toBeDefined());
    expect(await screen.findByText(/orders.nope/)).toBeInTheDocument();
    expect(inEditor().getByLabelText("What it means")).toHaveValue("Something else.");
  });

  it("shows a refused save inside the editor, not at the top of the page", async () => {
    // Found by the owner on the manual walk.
    const calls = stubFetch({
      definitions: json([BINDING]),
      patch: json({ detail: "'net_revenue' requires a filter on orders.nope" }, 400),
    });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(inEditor().getByLabelText("What it means"), {
      target: { value: "Something else." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(bodyOf(calls, "PATCH")).toBeDefined());

    const card = (await screen.findByRole("button", { name: "Save changes" })).closest("li");
    expect(card).not.toBeNull();
    expect(within(card!).getByText(/orders.nope/)).toBeInTheDocument();
  });

  it("asks twice before taking a definition out of force", async () => {
    // Retiring changes what the platform enforces on every query that follows.
    const calls = stubFetch({ definitions: json([BINDING]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Retire" }));

    expect(calls.some((call) => call.init.method === "DELETE")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Confirm: take out of force" }));

    await waitFor(() =>
      expect(calls.some((call) => call.init.method === "DELETE")).toBe(true),
    );
  });

  it("shows which version is in force, and what the earlier ones said", async () => {
    // A definition binds, so "what did it require when that answer was written" is a question...
    stubFetch({
      definitions: json([BINDING]),
      versions: json([
        {
          version: 1,
          change: "created",
          name: "net_revenue",
          description: "Revenue.",
          expression: null,
          caveat: null,
          required_filters: [],
          synonyms: [],
          status: "active",
          changed_by: "u1",
          changed_at: "2026-08-17T10:00:00Z",
        },
        {
          version: 2,
          change: "updated",
          name: "net_revenue",
          description: "Revenue excluding cancelled and refunded orders.",
          expression: null,
          caveat: null,
          required_filters: BINDING.required_filters,
          synonyms: [],
          status: "active",
          changed_by: "u1",
          changed_at: "2026-08-18T10:00:00Z",
        },
      ]),
    });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    expect(await screen.findByText("v2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "History" }));

    expect(await screen.findByText(/v1 — written by hand, enforced nothing/)).toBeInTheDocument();
    expect(screen.getByText(/v2 — edited, enforced orders.status/)).toBeInTheDocument();
  });

  it("shows what is out of force, so there is something to bring back", async () => {
    // B-094's other half. Retiring made a definition vanish from every view.
    stubFetch({ definitions: json([]), retired: json([{ ...BINDING, version: 5 }]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(await screen.findByText("Out of force")).toBeInTheDocument();
    expect(screen.getByText("retired")).toBeInTheDocument();
    expect(screen.getByText("v5")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reinstate" })).toBeInTheDocument();
  });

  it("hides the out-of-force card when there is nothing in it", async () => {
    // An ordinary organization never sees it.
    stubFetch({ definitions: json([BINDING]), retired: json([]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(await screen.findByText("net_revenue")).toBeInTheDocument();
    expect(screen.queryByText("Out of force")).not.toBeInTheDocument();
  });

  it("brings a retired definition back with one click", async () => {
    const calls = stubFetch({ definitions: json([]), retired: json([{ ...BINDING, version: 5 }]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Reinstate" }));

    await waitFor(() =>
      expect(
        calls.some((call) => call.url.endsWith("/reinstate") && call.init.method === "POST"),
      ).toBe(true),
    );
    // No filters sent: the API reads an absent list as "as it was retired".
    expect(bodyOf(calls, "POST")).toEqual({});
  });

  it("says being listed is not being in force", async () => {
    // The card is a way back, not a back door.
    stubFetch({ definitions: json([]), retired: json([{ ...BINDING, version: 5 }]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);

    expect(await screen.findByText(/None of this constrains anything/)).toBeInTheDocument();
    expect(screen.getByText(/Reinstated, it binds again/)).toBeInTheDocument();
  });

  it("says plainly when a definition has no recorded history", async () => {
    // One written before the platform kept a history.
    stubFetch({ definitions: json([BINDING]), versions: json([]) });

    render(<Definitions orgId="org-1" dataSourceId="ds-1" role="admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "History" }));

    expect(await screen.findByText(/Nothing recorded/)).toBeInTheDocument();
  });
});
