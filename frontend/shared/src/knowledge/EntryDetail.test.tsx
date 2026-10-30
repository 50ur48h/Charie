import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { EntryDetail } from "./EntryDetail";
import { getMockKnowledge } from "../mocks/sampleKnowledge";

afterEach(cleanup);

const netSales = getMockKnowledge("metric.net_sales")!;

describe("EntryDetail", () => {
  test("read_only: full evidence with a suggest action and no edit controls", () => {
    render(<EntryDetail entry={netSales} version={14} history={[]} onSuggest={vi.fn()} />);
    expect(screen.getByText("Net sales")).not.toBeNull();
    expect(screen.getByText("Confirmed by you")).not.toBeNull();
    expect(screen.getByText("Version 14")).not.toBeNull();
    expect(screen.getByText("How it's worked out")).not.toBeNull();
    expect(screen.queryByRole("button", { name: /Edit/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Approve/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Mark as wrong/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Suggest a change" })).not.toBeNull();
  });

  test("source_and_recipe: quotes and checks render from fixtures", () => {
    render(<EntryDetail entry={netSales} version={14} history={[]} onSuggest={vi.fn()} />);
    expect(
      screen.getByText(/order value after discounts/),
    ).not.toBeNull();
    expect(screen.getByText(/Matches the finance report/)).not.toBeNull();
    const sql = screen.getByText(/SUM\(o.total/);
    expect(sql.tagName).toBe("PRE");
  });

  test("minimal entries fall back to short meaning", async () => {
    const user = userEvent.setup();
    const onSuggest = vi.fn();
    const lunch = getMockKnowledge("default.lunch")!;
    render(<EntryDetail entry={lunch} version={14} history={[]} onSuggest={onSuggest} />);
    expect(screen.getByText("Orders placed between 11 am and 3 pm.")).not.toBeNull();
    expect(screen.queryByText("How it's worked out")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Suggest a change" }));
    expect(onSuggest).toHaveBeenCalled();
  });

  test("editable: shows Edit, Mark as wrong and Approve with the draft version", () => {
    const lunch = getMockKnowledge("metric.labor_cost_percent")!;
    render(
      <EntryDetail
        entry={lunch}
        version={{ number: 15, status: "draft" }}
        history={[]}
        editable
        onSuggest={vi.fn()}
        onStartEdit={vi.fn()}
        onApprove={vi.fn()}
        onWrong={vi.fn()}
      />,
    );
    expect(screen.getByText("Draft version 15")).not.toBeNull();
    expect(screen.getByRole("button", { name: /Edit/ })).not.toBeNull();
    expect(screen.getByRole("button", { name: "Mark as wrong" })).not.toBeNull();
    expect(screen.getByRole("button", { name: "Approve" })).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Suggest a change" })).toBeNull();
  });

  test("editable: Approve is disabled when confirmed", () => {
    const onApprove = vi.fn();
    const { rerender } = render(
      <EntryDetail
        entry={netSales}
        version={{ number: 15, status: "draft" }}
        history={[]}
        editable
        onSuggest={vi.fn()}
        onApprove={onApprove}
      />,
    );
    const approve = screen.getByRole("button", { name: "Approve" });
    expect(approve.hasAttribute("disabled")).toBe(true);
    expect(approve.getAttribute("title")).toBe("Already confirmed by you");
    const guess = getMockKnowledge("metric.labor_cost_percent")!;
    rerender(
      <EntryDetail
        entry={guess}
        version={{ number: 15, status: "draft" }}
        history={[]}
        editable
        onSuggest={vi.fn()}
        onApprove={onApprove}
      />,
    );
    expect(screen.getByRole("button", { name: "Approve" }).hasAttribute("disabled")).toBe(false);
  });

  test("editable: the published version label stays", () => {
    render(
      <EntryDetail
        entry={netSales}
        version={{ number: 14, status: "published" }}
        history={[]}
        editable
        onSuggest={vi.fn()}
      />,
    );
    expect(screen.getByText("Version 14")).not.toBeNull();
  });
  test("real entry: details, typed sources and history render", () => {
    render(
      <EntryDetail
        entry={{
          key: "table.public.orders",
          kind: "table",
          title: "orders",
          meaning: "A table with about 400K rows and 9 columns.",
          confidence: "checked",
          details: { schema: "public", name: "orders", row_estimate: 400000 },
          sources: [
            { type: "structure", text: "Read from the database structure" },
            {
              type: "query",
              text: "Tested with a query",
              sql: "SELECT count(*) FROM orders",
            },
          ],
          updated_at: null,
        }}
        version={{ number: 1, status: "published" }}
        history={[{ version: 1, change: "added", reason: "First learning" }]}
        onSuggest={vi.fn()}
      />,
    );
    expect(screen.getByText("Table")).not.toBeNull();
    expect(screen.getByText("About 400K rows")).not.toBeNull();
    expect(screen.getByText("Read from the database structure")).not.toBeNull();
    expect(screen.getByText("Show the query")).not.toBeNull();
    expect(screen.getByText("Version 1 · First learning")).not.toBeNull();
    expect(screen.queryByText("Used in")).toBeNull();
  });
});