import { describe, expect, it } from "vitest";

import { markTone, isDeltaColumn, looksNumeric, numberIn } from "./cells";
import { buildChart, humanize, readChartTheme } from "./chart-option";
import { deriveChart, periodOf } from "./table-chart";

type Series = { type: string; lineStyle?: { color?: string }; itemStyle?: { color?: string }; data: unknown[] };

describe("the chart translator", () => {
  it("gives each series of a split chart its own colour, from the palette (B-109)", () => {
    /** Every chart used to be the primary colour and nothing else. */
    const outlets = ["A", "B", "C", "D", "E", "F", "G", "H"];
    const values = outlets.flatMap((outlet, index) => [
      { month: "2026-05-01", revenue: 100 + index, outlet },
      { month: "2026-06-01", revenue: 120 + index, outlet },
    ]);
    const built = buildChart(
      {
        mark: "line",
        encoding: {
          x: { field: "month", type: "temporal", timeUnit: "yearmonth" },
          y: { field: "revenue", type: "quantitative" },
          color: { field: "outlet", type: "nominal" },
        },
        data: { values },
      },
      readChartTheme(),
    );

    const colours = (built?.option.series as Series[]).map((series) => series.lineStyle?.color);
    expect(colours).toHaveLength(8);
    expect(new Set(colours).size).toBe(8);
  });

  it("draws a change that goes both ways as diverging bars, and calls out the biggest fall", () => {
    const built = buildChart(
      {
        mark: "bar",
        encoding: {
          x: { field: "restaurant", type: "nominal" },
          y: { field: "change_pct", type: "quantitative", title: "Change (%)" },
        },
        data: {
          values: [
            { restaurant: "Dallas Uptown", change_pct: 14.8 },
            { restaurant: "Galleria", change_pct: -2.4 },
            { restaurant: "Downtown Austin", change_pct: -18.2 },
          ],
        },
      },
      readChartTheme(),
    );

    const yAxis = built?.option.yAxis as { data: string[]; axisLabel: { formatter: (v: string) => string } };
    // Sorted so the biggest fall sits at the bottom, as the design draws it.
    expect(yAxis.data[0]).toBe("Downtown Austin");
    expect(yAxis.axisLabel.formatter("Downtown Austin")).toBe("{hl|Downtown Austin}");
    expect(yAxis.axisLabel.formatter("Galleria")).toBe("Galleria");
  });

  it("labels time the way a person says it, in order", () => {
    const built = buildChart(
      {
        mark: "line",
        encoding: {
          x: { field: "order_month", type: "temporal", timeUnit: "yearmonth" },
          y: { field: "order_count", type: "quantitative" },
        },
        data: {
          values: [
            { order_month: "2026-07-01", order_count: 3857 },
            { order_month: "2026-05-01", order_count: 3624 },
            { order_month: "2026-06-01", order_count: 4125 },
          ],
        },
      },
      readChartTheme(),
    );

    expect((built?.option.xAxis as { data: string[] }).data).toEqual(["May 2026", "Jun 2026", "Jul 2026"]);
    expect((built?.option.series as Series[])[0]?.data).toEqual([3624, 4125, 3857]);
    expect(built?.title).toBe("Order count by order month");
    expect(built?.subtitle).toBe("May 2026 – Jul 2026");
  });

  it("refuses a spec outside the vocabulary rather than guessing", () => {
    const theme = readChartTheme();
    expect(buildChart({ mark: "arc", encoding: {}, data: { values: [] } }, theme)).toBeNull();
    expect(
      buildChart(
        { mark: "bar", encoding: { x: { field: "a", type: "nominal" } }, data: { values: [{ a: 1 }] } },
        theme,
      ),
    ).toBeNull();
  });

  it("titles a column the way a reader would", () => {
    expect(humanize("order_month")).toBe("Order month");
  });
});

describe("how an emphasised phrase reads", () => {
  it("marks a phrase with a number and a direction", () => {
    expect(markTone("up 6.2%")).toBe("up");
    expect(markTone("Downtown Austin, down 18.2%")).toBe("down");
    expect(markTone("−$21.4K")).toBe("down");
    expect(markTone("+4.1%")).toBe("up");
  });

  it("leaves a name, a plain figure, or a mixed phrase alone", () => {
    expect(markTone("Sup Buntut")).toBeNull();
    expect(markTone("$1.42M")).toBeNull();
    expect(markTone("likely cause")).toBeNull();
    expect(markTone("up 3% and down 2%")).toBeNull();
  });
});

describe("how a table cell reads", () => {
  it("knows a number from a word", () => {
    expect(looksNumeric("$1,234.50")).toBe(true);
    expect(looksNumeric("RM737.68")).toBe(true);
    expect(looksNumeric("−18.2%")).toBe(true);
    expect(looksNumeric("2025-12")).toBe(false);
    expect(looksNumeric("Ayam Penyet")).toBe(false);
  });

  it("sorts by the number a cell stands for", () => {
    expect(numberIn("$88.4K")).toBe(88400);
    expect(numberIn("(1,200)")).toBe(-1200);
    expect(numberIn("−2.4%")).toBe(-2.4);
  });

  it("treats a column of signed percentages as changes", () => {
    expect(isDeltaColumn("vs last month", ["+14.8%", "−2.4%"])).toBe(true);
    expect(isDeltaColumn("Orders", ["2,705", "1,968"])).toBe(false);
  });
});

describe("a chart drawn from an answer's own table", () => {
  it("plots matching sales columns together, excluding orders and comparison notes", () => {
    const derived = deriveChart(
      ["Month", "Outlet A orders", "Outlet A sales", "Outlet B orders", "Outlet B sales", "Ahead"],
      [["Jan 2025", "10", "1,000", "20", "900", "A"],
        ["Feb 2025", "12", "1,200", "22", "1,300", "B"],
        ["Mar 2025", "14", "1,400", "24", "1,100", "A"]],
    );
    const built = buildChart(derived!.spec, readChartTheme());
    const series = built!.option.series as (Series & { name: string })[];
    expect(series.map(({ name, data }) => ({ name, data }))).toEqual([
      { name: "Outlet A sales", data: [1000, 1200, 1400] },
      { name: "Outlet B sales", data: [900, 1300, 1100] },
    ]);
    expect(built!.title).toBe("Sales by month");
    expect(built!.option.legend).toBeDefined();
    expect(new Set(series.map((entry) => entry.lineStyle?.color)).size).toBe(2);
  });

  it("does not combine different currencies or sales definitions", () => {
    for (const [headers, amounts] of [
      [["Outlet A sales", "Outlet B sales"], ["$100", "€200"]],
      [["Outlet A net sales", "Outlet B gross sales"], ["$100", "$200"]],
    ]) {
      const derived = deriveChart(["Month", ...headers!],
        ["Jan 2025", "Feb 2025", "Mar 2025"].map((month) => [month, ...amounts!]));
      const built = buildChart(derived!.spec, readChartTheme());
      expect(built!.option.series as Series[]).toHaveLength(1);
    }
  });

  it("draws a period against a figure as a line, in the table's own unit", () => {
    const derived = deriveChart(
      ["Month", "Total sales"],
      [
        ["January 2025", "RM 1,058,564"],
        ["February 2025", "RM 1,012,250"],
        ["March 2025", "RM 1,133,578"],
      ],
    );
    expect(derived?.spec.mark).toBe("line");
    expect(derived?.spec.usermeta).toEqual({ prefix: "RM ", suffix: "" });
    const built = buildChart(derived!.spec, readChartTheme());
    expect((built?.option.xAxis as { data: string[] }).data).toEqual(["Jan 2025", "Feb 2025", "Mar 2025"]);
    expect((built?.option.series as Series[])[0]?.data).toEqual([1058564, 1012250, 1133578]);
  });

  it("plots a change column when there is one, as the design's diverging bars", () => {
    const derived = deriveChart(
      ["Restaurant", "November", "December", "Change"],
      [
        ["Grimes Inc", "RM 24,000", "RM 26,640", "+11.0%"],
        ["Galleria", "RM 20,000", "RM 19,520", "-2.4%"],
        ["Kovacek", "RM 30,000", "RM 25,020", "-16.6%"],
      ],
    );
    expect(derived?.value).toBe("Change");
    expect(derived?.spec.usermeta).toEqual({ prefix: "", suffix: "%" });
    const yAxis = buildChart(derived!.spec, readChartTheme())?.option.yAxis as { data: string[] };
    expect(yAxis.data[0]).toBe("Kovacek");
  });

  it("leaves a table alone when it is too small or has nothing to plot", () => {
    expect(deriveChart(["Product", "Waste RM"], [["Peha", "64.59"]])).toBeNull();
    expect(deriveChart(["Name", "Note"], [["a", "x"], ["b", "y"], ["c", "z"]])).toBeNull();
  });

  it("reads the periods people write", () => {
    expect(periodOf("March 2025")?.iso).toBe("2025-03-01");
    expect(periodOf("Sep 2025")?.iso).toBe("2025-09-01");
    expect(periodOf("2025-12")?.iso).toBe("2025-12-01");
    expect(periodOf("Q1 2025")).toBeNull();
  });
});
