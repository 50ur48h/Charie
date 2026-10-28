import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { EntryDetail } from "./EntryDetail";
import { getMockKnowledge } from "../mocks/sampleKnowledge";

afterEach(cleanup);

const netSales = getMockKnowledge("metric.net_sales")!;

describe("EntryDetail", () => {
  test("read_only: full evidence with a suggest action and no edit controls", () => {
    render(<EntryDetail entry={netSales} version={14} onSuggest={vi.fn()} />);
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
    render(<EntryDetail entry={netSales} version={14} onSuggest={vi.fn()} />);
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
    render(<EntryDetail entry={lunch} version={14} onSuggest={onSuggest} />);
    expect(screen.getByText("Orders placed between 11 am and 3 pm.")).not.toBeNull();
    expect(screen.queryByText("How it's worked out")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Suggest a change" }));
    expect(onSuggest).toHaveBeenCalled();
  });
});
