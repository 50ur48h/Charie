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
