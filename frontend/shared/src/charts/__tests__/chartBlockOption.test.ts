import { describe, expect, test } from "vitest";
import { buildChartOption } from "../chartBlockOption";
import { light } from "./fixtures";
import type { ChartBlock } from "../../api/chat-types";

function diverging(): ChartBlock {
  return {
    type: "chart",
    kind: "bar_diverging",
    title: "Sales change by restaurant",
    subtitle: "Oct vs Sep 2025",
    x: "restaurant",
    y: "change",
    unit: "percent",
    highlight: ["Downtown"],
    data: {
      columns: ["restaurant", "change"],
      rows: [
        ["Downtown", { v: -18.2, f: "−18.2%" }],
        ["Uptown", { v: 9.4, f: "+9.4%" }],
      ],
    },
  };
}

describe("buildChartOption", () => {
  test("plots_v_labels_f", () => {
    const bar = buildChartOption({ ...diverging(), kind: "bar" }, light);
    expect(bar).not.toBeNull();
    const option = bar?.option as {
      series: [{ data: { value: number; label: { formatter: string } }[] }];
      tooltip: { valueFormatter: (v: number) => string };
    };
    expect(option.series[0].data.map((d) => d.value).sort((a, b) => a - b)).toEqual([
      -18.2, 9.4,
    ]);
    // Labels and tooltips show the backend's formatted strings, never
    // recomputed ones.
    expect(
      option.series[0].data.map((d) => d.label.formatter).sort(),
    ).toEqual(["+9.4%", "−18.2%"]);
    expect(option.tooltip.valueFormatter(-18.2)).toBe("−18.2%");
    expect(option.tooltip.valueFormatter(9.4)).toBe("+9.4%");
    const figure = buildChartOption(diverging(), light);
    const divergingOption = figure?.option as {
      series: [{ data: { value: number }[] }];
      tooltip: { formatter: (p: { name: string } | { name: string }[]) => string };
    };
    expect(
      divergingOption.series[0].data.map((d) => d.value).sort((a, b) => a - b),
    ).toEqual([-18.2, 9.4]);
    expect(divergingOption.tooltip.formatter({ name: "Downtown" })).toContain("−18.2%");
  });

  test("preserves_order", () => {
    const figure = buildChartOption(
      {
        type: "chart",
        kind: "line",
        title: "Delivery orders per day",
        x: "day",
        y: "orders",
        unit: "count",
        data: {
          columns: ["day", "orders"],
          rows: [
            ["3 Oct", { v: 224, f: "224" }],
            ["1 Oct", { v: 301, f: "301" }],
            ["2 Oct", { v: 287, f: "287" }],
          ],
        },
      },
      light,
    );
    const option = figure?.option as {
      xAxis: { data: string[] };
      series: [{ data: (number | null)[] }];
    };
    // Server category order survives: no value re-sorting for lines.
    expect(option.xAxis.data).toEqual(["3 Oct", "1 Oct", "2 Oct"]);
    expect(option.series[0].data).toEqual([224, 301, 287]);
  });

  test("handles_empty", () => {
    for (const kind of ["bar", "bar_diverging", "line", "bar_stacked"]) {
      const figure = buildChartOption(
        {
          type: "chart",
          kind,
          title: "Empty",
          x: "x",
          y: "y",
          unit: "count",
          data: { columns: ["x", "y"], rows: [] },
        },
        light,
      );
      expect(figure).not.toBeNull();
      const option = figure?.option as { series: [{ data: unknown[] }] };
      expect(option.series[0].data).toEqual([]);
    }
    expect(
      buildChartOption({ ...diverging(), kind: "pie" }, light),
    ).toBeNull();
  });

  test("drops null bars but gaps null line points", () => {
    const block = diverging();
    block.data.rows.push(["Nowhere", null]);
    const figure = buildChartOption(block, light);
    const option = figure?.option as { series: [{ data: { value: number }[] }] };
    expect(option.series[0].data.map((d) => d.value)).toEqual([-18.2, 9.4]);
    const line = buildChartOption(
      {
        type: "chart",
        kind: "line",
        title: "Gaps",
        x: "day",
        y: "orders",
        unit: "count",
        data: {
          columns: ["day", "orders"],
          rows: [
            ["1 Oct", { v: 301, f: "301" }],
            ["2 Oct", null],
          ],
        },
      },
      light,
    );
    const lineOption = line?.option as { series: [{ data: (number | null)[] }] };
    expect(lineOption.series[0].data).toEqual([301, null]);
  });

  test("preserves_server_order", () => {
    const shuffled: ChartBlock = {
      ...diverging(),
      data: {
        columns: ["restaurant", "change"],
        rows: [
          ["Uptown", { v: 9.4, f: "+9.4%" }],
          ["Downtown", { v: -18.2, f: "−18.2%" }],
          ["Midtown", { v: 2.1, f: "+2.1%" }],
        ],
      },
    };
    for (const kind of ["bar", "bar_diverging"]) {
      const figure = buildChartOption({ ...shuffled, kind }, light);
      const option = figure?.option as {
        yAxis: { data: string[] };
        series: [{ data: { value: number }[] }];
      };
      // Server order survives the kit: categories, values and the
      // highlight stay aligned instead of value-sorted.
      expect(option.yAxis.data).toEqual(["Uptown", "Downtown", "Midtown"]);
      expect(option.series[0].data.map((d) => d.value)).toEqual([9.4, -18.2, 2.1]);
    }
    const barFigure = buildChartOption({ ...shuffled, kind: "bar" }, light);
    const barOption = barFigure?.option as {
      tooltip: { valueFormatter: (v: number, i?: number) => string };
    };
    expect(barOption.tooltip.valueFormatter(-18.2, 1)).toBe("−18.2%");
    const divergingFigure = buildChartOption({ ...shuffled, kind: "bar_diverging" }, light);
    const divergingOption = divergingFigure?.option as {
      tooltip: { formatter: (p: { name: string }) => string };
    };
    expect(divergingOption.tooltip.formatter({ name: "Downtown" })).toContain("−18.2%");
  });

  test("formatted_x_cells", () => {
    const figure = buildChartOption(
      {
        type: "chart",
        kind: "bar",
        title: "Sales by month",
        x: "month",
        y: "sales",
        unit: "money",
        currency: "USD",
        highlight: ["Oct"],
        data: {
          columns: ["month", "sales"],
          rows: [
            [{ v: 9, f: "Sep" }, { v: 80000, f: "$80K" }],
            [{ v: 10, f: "Oct" }, { v: 96200, f: "$96.2K" }],
          ],
        },
      },
      light,
    );
    const option = figure?.option as {
      yAxis: {
        data: string[];
        axisLabel: { formatter: (v: string) => string };
      };
      series: [{ data: { value: number }[] }];
    };
    // Categories show f, values plot v, highlights match the f label.
    expect(option.yAxis.data).toEqual(["Sep", "Oct"]);
    expect(option.series[0].data.map((d) => d.value)).toEqual([80000, 96200]);
    expect(option.yAxis.axisLabel.formatter("Oct")).toContain("hl");
    expect(option.yAxis.axisLabel.formatter("Sep")).toBe("Sep");
  });

  test("equal_values_distinct_labels", () => {
    const figure = buildChartOption(
      {
        type: "chart",
        kind: "bar",
        title: "Tied",
        x: "team",
        y: "score",
        unit: "count",
        data: {
          columns: ["team", "score"],
          rows: [
            ["Alpha", { v: 5, f: "5 (first)" }],
            ["Beta", { v: 5, f: "5 (second)" }],
          ],
        },
      },
      light,
    );
    const option = figure?.option as {
      tooltip: { valueFormatter: (v: number, i?: number) => string };
    };
    // Points are identified by row, not by numeric value alone.
    expect(option.tooltip.valueFormatter(5, 0)).toBe("5 (first)");
    expect(option.tooltip.valueFormatter(5, 1)).toBe("5 (second)");
  });

  test("small_tick_precision", () => {
    const percent = buildChartOption({ ...diverging(), unit: "percent" }, light);
    const percentAxis = (percent?.option as {
      xAxis: { axisLabel: { formatter: (v: number) => string } };
    }).xAxis.axisLabel.formatter;
    expect(percentAxis(18.24)).toBe("18.2%");
    expect(percentAxis(18.26)).toBe("18.3%");
    expect(percentAxis(20)).toBe("20%");
    const ratio = buildChartOption({ ...diverging(), unit: "ratio" }, light);
    const ratioAxis = (ratio?.option as {
      xAxis: { axisLabel: { formatter: (v: number) => string } };
    }).xAxis.axisLabel.formatter;
    expect(ratioAxis(1.421)).toBe("1.421");
    expect(ratioAxis(1.429)).toBe("1.429");
    expect(ratioAxis(2)).toBe("2");
  });

  test("adds narrow-screen ticks for bars without touching laptop rendering", () => {
    const figure = buildChartOption(diverging(), light);
    const option = figure?.option as {
      media: [{ query: { maxWidth: number }; option: { xAxis: { splitNumber: number } } }];
    };
    expect(option.media).toHaveLength(1);
    expect(option.media[0].query.maxWidth).toBe(480);
    expect(option.media[0].option.xAxis.splitNumber).toBe(2);
  });
});
