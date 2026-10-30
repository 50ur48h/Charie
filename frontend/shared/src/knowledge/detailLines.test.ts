import { describe, expect, test } from "vitest";
import { detailLines } from "./detailLines";

// One test per kind with details (P07.4), plus missing data left out.
describe("detailLines", () => {
  test("table names the view, rows, columns, key and sample", () => {
    expect(
      detailLines("table", {
        schema: "public",
        name: "orders",
        is_view: false,
        row_estimate: 400000,
        columns: ["id", "total", "status"],
        primary_key: ["id"],
        sampled: true,
        rows_profiled: 200000,
        grain: "one order",
      }),
    ).toEqual([
      "Table",
      "About 400K rows",
      "3 columns",
      "Key: id",
      "Looked at 200K rows (a sample)",
      "One row is: one order",
    ]);
    expect(detailLines("table", { schema: "public", name: "v", is_view: true })).toEqual([
      "View (a saved query)",
    ]);
  });

  test("column formats the profile", () => {
    expect(
      detailLines("column", {
        schema: "public",
        table: "orders",
        name: "status",
        data_type: "text",
        nullable: false,
        profile: {
          empty_share: 0.012,
          distinct: 397000,
          min: 3.2,
          max: 412.55,
          pattern: "AAAA9999",
          pattern_share: 0.96,
          strict: false,
          top_values: [
            { value: "completed", count: 81 },
            { value: "cancelled", count: 12 },
            { value: "refunded", count: 7 },
          ],
        },
        refers_to: "restaurants",
        unit: "g",
        currency: "USD",
      }),
    ).toEqual([
      "Type: text",
      "Never empty",
      "Empty: 1.2%",
      "Different values: 397K",
      "Smallest: 3.2 · Largest: 412.55",
      "Pattern: AAAA9999 (96% of values)",
      "Most common: completed (81%), cancelled (12%), refunded (7%)",
      "Points to restaurants",
      "Unit: g",
      "Currency: USD",
    ]);
  });

  test("column dates and strict mode", () => {
    const lines = detailLines("column", {
      schema: "public",
      table: "orders",
      name: "created_at",
      data_type: "timestamp",
      nullable: true,
      profile: { date_from: "2024-01-01", date_to: "2025-12-31", strict: true },
    });
    expect(lines).toContain("Can be empty");
    expect(lines).toContain("Dates: 1 Jan 2024 to 31 Dec 2025");
    expect(lines).toContain("Example values not kept (strict mode)");
    expect(lines.some((line) => line.startsWith("Most common"))).toBe(false);
  });

  test("link names the join and how it was found", () => {
    expect(
      detailLines("link", {
        from_table: "orders",
        from_columns: ["restaurant_id"],
        to_table: "restaurants",
        to_columns: ["id"],
        found_by: "foreign_key",
        cardinality: "many_to_one",
        match_share: 1,
        sampled: true,
      }),
    ).toEqual([
      "From orders.restaurant_id to restaurants.id",
      "Many rows here can point to the same row there",
      "Rows that match: 100%",
      "Found from a foreign key",
      "Tested on a sample",
    ]);
    expect(
      detailLines("link", {
        from_table: "a",
        from_columns: ["x"],
        to_table: "b",
        to_columns: ["y"],
        found_by: "matching_name",
        cardinality: "one_to_one",
      })[1],
    ).toBe("Each row here matches at most one row there");
  });

  test("data range names the dates and the sample", () => {
    expect(
      detailLines("data_range", {
        table: "orders",
        date_column: "created_at",
        date_from: "2024-01-01",
        date_to: "2025-12-31",
        exact: false,
      }),
    ).toEqual([
      "Dates from 1 Jan 2024 to 31 Dec 2025",
      "Main date column: created_at",
      "Measured on a sample",
    ]);
  });

  test("rule spells out each rule type", () => {
    expect(detailLines("rule", { rule_type: "never_use_table", table: "orders_old" })).toEqual([
      "Never use the table orders_old",
    ]);
    expect(
      detailLines("rule", {
        rule_type: "always_filter",
        column: "status",
        values: ["completed"],
      }),
    ).toEqual(["Only rows where status is completed"]);
    expect(
      detailLines("rule", { rule_type: "exclude_values", column: "id", values: ["9001", "9002"] }),
    ).toEqual(["Leave out rows where id is 9001, 9002"]);
    expect(detailLines("rule", { rule_type: "currency", currency: "USD" })).toEqual([
      "Money is in USD",
    ]);
    expect(
      detailLines("rule", { rule_type: "required_note", note_text: "Illustrative, not audited profit" }),
    ).toEqual(["Add this note: “Illustrative, not audited profit”"]);
  });

  test("style and name lists", () => {
    expect(detailLines("style", { topics: ["profit"] })).toEqual(["When: profit"]);
    expect(detailLines("style", {})).toEqual(["Always"]);
    expect(
      detailLines("name", {
        table: "restaurants",
        id_column: "id",
        name_column: "name",
        items: new Array(60).fill({ id: 1, name: "x" }),
        truncated: true,
      }),
    ).toEqual(["60 names from restaurants.name, first 1,000 only"]);
  });

  test("other kinds have none, and missing data is left out", () => {
    for (const kind of ["metric", "dimension", "code", "event", "data_problem", "default", "calendar", "how_to", "example"] as const) {
      expect(detailLines(kind, { anything: 1 })).toEqual([]);
    }
    expect(detailLines("table", null)).toEqual(["Table"]);
    expect(detailLines("column", {})).toEqual([]);
    expect(detailLines("column", { data_type: "text", profile: {} })).toEqual(["Type: text"]);
    expect(detailLines("data_range", { table: "orders", exact: true })).toEqual([]);
  });
});
