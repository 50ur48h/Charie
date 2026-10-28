import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "./DataTable";

afterEach(cleanup);

interface Question {
  question: string;
  date: string;
  thinking: string;
  steps: number;
  cost: string;
}

const COLUMNS: ColumnDef<Question>[] = [
  {
    header: "Question",
    accessorKey: "question",
    cell: (info) => (
      <span>
        {info.row.original.question}
        <small className="block text-muted">{info.row.original.date}</small>
      </span>
    ),
  },
  { header: "Thinking time", accessorKey: "thinking" },
  { header: "AI steps", accessorKey: "steps", meta: { numeric: true } },
  { header: "Cost", accessorKey: "cost", meta: { numeric: true } },
];

const ROWS: Question[] = [
  { question: "Why did sales dip?", date: "26 Oct", thinking: "Deep", steps: 14, cost: "$2.10" },
  { question: "Best coupon?", date: "25 Oct", thinking: "Quick", steps: 3, cost: "$0.40" },
];

describe("DataTable", () => {
  test("shows a row for each item", () => {
    render(<DataTable columns={COLUMNS} data={ROWS} caption="Most expensive questions" />);
    expect(screen.getByText("Why did sales dip?")).toBeTruthy();
    expect(screen.getByText("Best coupon?")).toBeTruthy();
  });

  test("right-aligns numeric columns", () => {
    render(<DataTable columns={COLUMNS} data={ROWS} caption="Most expensive questions" />);
    const table = screen.getByRole("table");
    const costHeader = within(table).getByRole("columnheader", { name: "Cost" });
    expect(costHeader.className).toContain("text-right");
    const costCell = within(table).getByRole("cell", { name: "$2.10" });
    expect(costCell.className).toContain("text-right");
  });

  test("shows the empty text when there are no rows", () => {
    render(
      <DataTable
        columns={COLUMNS}
        data={[]}
        empty="No documents yet. Drop files here to start."
        caption="Documents"
      />,
    );
    expect(screen.getByText("No documents yet. Drop files here to start.")).toBeTruthy();
  });
});
