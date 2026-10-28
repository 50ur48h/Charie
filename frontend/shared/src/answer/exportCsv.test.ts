import { describe, expect, test } from "vitest";
import { tableCsv, tableFileName } from "./exportCsv";
import type { TableBlock } from "../api/chat-types";

function block(): TableBlock {
  return {
    type: "table",
    title: "Top 5 restaurants",
    columns: [
      { key: "restaurant", label: "Restaurant" },
      { key: "sales", label: "Net sales", unit: "money" },
    ],
    rows: [],
  };
}

describe("tableCsv", () => {
  test("escaping", () => {
    const csv = tableCsv({
      ...block(),
      rows: [
        { restaurant: 'Downtown, "East"', sales: { v: 78400, f: "$78.4K" } },
        { restaurant: "Line one\nLine two", sales: { v: 100, f: "$100" } },
      ],
    });
    expect(csv).toBe(
      "\uFEFFRestaurant,Net sales\r\n" +
        '"Downtown, ""East""",78400\r\n' +
        '"Line one\nLine two",100\r\n',
    );
  });

  test("formula_text", () => {
    const csv = tableCsv({
      ...block(),
      rows: [
        { restaurant: "=SUM(A1:A2)", sales: { v: 1, f: "$1" } },
        { restaurant: "@mention", sales: { v: 2, f: "$2" } },
      ],
    });
    expect(csv).toContain("'=SUM(A1:A2)");
    expect(csv).toContain("'@mention");
  });

  test("negative_number", () => {
    const csv = tableCsv({
      ...block(),
      rows: [{ restaurant: "Downtown", sales: { v: -18400, f: "−$18.4K" } }],
    });
    // Raw value, no formula guard, no quotes: still a number downstream.
    expect(csv).toContain(",-18400\r\n");
  });

  test("file name", () => {
    expect(tableFileName("Top 5 restaurants")).toBe("top-5-restaurants.csv");
    expect(tableFileName("")).toBe("table.csv");
  });
});
